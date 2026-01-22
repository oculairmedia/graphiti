import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import CommunityEdge
from graphiti_core.embedder import EmbedderClient
from graphiti_core.helpers import semaphore_gather
from graphiti_core.llm_client import LLMClient
from graphiti_core.nodes import CommunityNode, EntityNode, get_community_node_from_record
from graphiti_core.prompts import prompt_library
from graphiti_core.prompts.models import Message
from graphiti_core.prompts.summarize_nodes import Summary, SummaryDescription
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.maintenance.edge_operations import build_community_edges

MAX_COMMUNITY_BUILD_CONCURRENCY = 10

logger = logging.getLogger(__name__)


# =============================================================================
# Incremental Community Detection Types and Config
# =============================================================================


class CommunityScenario(Enum):
    """Scenarios for incremental community updates (from PRD)."""

    EXISTING_COMMUNITY = 'existing_community'  # Scenario A: Node joins existing community
    NEW_COMMUNITY = 'new_community'  # Scenario B: New community created
    MERGE_COMMUNITIES = 'merge_communities'  # Scenario C: Two communities merge
    NO_COMMUNITY = 'no_community'  # Node is isolated, no community action


@dataclass
class IncrementalCommunityConfig:
    """Configuration for IncrementalCommunityManager."""

    max_summary_tokens: int = 500
    enable_locking: bool = False  # For future Redis lock implementation
    lock_timeout_seconds: int = 30
    min_cluster_size: int = 2  # Minimum nodes to form a community


@dataclass
class ScenarioResult:
    """Result of scenario detection."""

    type: CommunityScenario
    community: Optional[CommunityNode] = None
    communities_to_merge: list[CommunityNode] = field(default_factory=list)
    cluster_members: list[str] = field(default_factory=list)


# =============================================================================
# Delta Summarization Prompts
# =============================================================================


class DeltaSummary(BaseModel):
    """Model for delta summary response."""

    summary: str


def delta_summary_prompt(
    existing_summary: str, new_node_name: str, new_node_summary: str
) -> list[Message]:
    """
    Generate prompt for incremental summary update (Ledger Update pattern from PRD).

    This approach uses O(1) tokens instead of O(N) by only including:
    - The existing community summary
    - The new node's information
    """
    return [
        Message(
            role='system',
            content='You are a helpful assistant that updates community summaries with new information.',
        ),
        Message(
            role='user',
            content=f"""
<CURRENT_COMMUNITY_SUMMARY>
{existing_summary}
</CURRENT_COMMUNITY_SUMMARY>

<NEW_INFORMATION>
Entity: "{new_node_name}"
Summary: {new_node_summary}
</NEW_INFORMATION>

<TASK>
Update the community summary to incorporate the new information.
Keep the summary concise (under 250 words) while preserving important existing details.
If the new information contradicts existing information, prefer the new information.
</TASK>
""",
        ),
    ]


def merge_summary_prompt(summary_a: str, summary_b: str) -> list[Message]:
    """
    Generate prompt for merging two community summaries (Scenario C).
    """
    return [
        Message(
            role='system',
            content='You are a helpful assistant that merges community summaries.',
        ),
        Message(
            role='user',
            content=f"""
<COMMUNITY_A_SUMMARY>
{summary_a}
</COMMUNITY_A_SUMMARY>

<COMMUNITY_B_SUMMARY>
{summary_b}
</COMMUNITY_B_SUMMARY>

<TASK>
Merge these two community summaries into a single coherent summary.
Preserve important information from both communities.
Identify common themes and consolidate related information.
Keep the merged summary concise (under 300 words).
</TASK>
""",
        ),
    ]


# =============================================================================
# Standalone Functions for Delta Summarization
# =============================================================================


async def generate_delta_summary(
    llm_client: LLMClient,
    existing_summary: str,
    new_node: EntityNode,
) -> str:
    """
    Generate an incremental summary update for a community.

    Args:
        llm_client: LLM client for generation
        existing_summary: Current community summary
        new_node: New node being added to the community

    Returns:
        Updated summary incorporating the new node
    """
    prompt = delta_summary_prompt(
        existing_summary=existing_summary,
        new_node_name=new_node.name,
        new_node_summary=new_node.summary or '',
    )

    response = await llm_client.generate_response(prompt, response_model=DeltaSummary)
    return response.get('summary', existing_summary)


async def generate_merge_summary(
    llm_client: LLMClient,
    summary_a: str,
    summary_b: str,
) -> str:
    """
    Generate a merged summary from two community summaries.

    Args:
        llm_client: LLM client for generation
        summary_a: First community summary
        summary_b: Second community summary

    Returns:
        Merged summary
    """
    prompt = merge_summary_prompt(summary_a, summary_b)
    response = await llm_client.generate_response(prompt, response_model=DeltaSummary)
    return response.get('summary', f'{summary_a}\n\n{summary_b}')


# =============================================================================
# IncrementalCommunityManager Class
# =============================================================================


class IncrementalCommunityManager:
    """
    Manages incremental community detection and summarization.

    This class implements the incremental community update logic from PRD:
    - Scenario A: Add node to existing community with delta summarization
    - Scenario B: Create new community when cluster has no existing community
    - Scenario C: Merge communities when a bridging node connects them

    Usage:
        manager = IncrementalCommunityManager(driver, llm_client, embedder)
        await manager.update_for_entity(new_entity_node)
    """

    def __init__(
        self,
        driver: GraphDriver,
        llm_client: LLMClient,
        embedder: EmbedderClient,
        config: Optional[IncrementalCommunityConfig] = None,
    ):
        self.driver = driver
        self.llm_client = llm_client
        self.embedder = embedder
        self.config = config or IncrementalCommunityConfig()

    async def update_for_entity(self, entity: EntityNode) -> Optional[CommunityNode]:
        """
        Main entry point: Update communities based on a new/modified entity.

        This method:
        1. Detects which scenario applies (A, B, or C)
        2. Executes the appropriate scenario handler
        3. Returns the resulting community (if any)

        Args:
            entity: The entity node to process

        Returns:
            The community node (created or updated), or None if no community action taken
        """
        try:
            scenario = await self.detect_scenario(entity)

            if scenario.type == CommunityScenario.NO_COMMUNITY:
                logger.debug(f'Entity {entity.uuid} has no community (isolated node)')
                return None

            if scenario.type == CommunityScenario.EXISTING_COMMUNITY:
                existing_community = scenario.community
                if existing_community is not None:
                    return await self.execute_scenario_a(entity, existing_community)

            if scenario.type == CommunityScenario.NEW_COMMUNITY:
                # Get full cluster for new community creation
                cluster_nodes = await EntityNode.get_by_uuids(self.driver, scenario.cluster_members)
                return await self.execute_scenario_b(cluster_nodes)

            if scenario.type == CommunityScenario.MERGE_COMMUNITIES:
                return await self.execute_scenario_c(entity, scenario.communities_to_merge)

        except Exception as e:
            logger.warning(f'Incremental community update failed for {entity.uuid}: {e}')
            # Graceful degradation - don't crash ingestion
            return None

        return None

    async def detect_scenario(self, entity: EntityNode) -> ScenarioResult:
        """
        Detect which scenario applies for the given entity.

        Uses native CDLP to find the entity's cluster, then checks:
        - If cluster members have an existing community -> Scenario A
        - If cluster members span multiple communities -> Scenario C
        - If no existing community for cluster -> Scenario B
        - If entity is isolated -> NO_COMMUNITY
        """
        # Run CDLP to find the entity's cluster
        records, _, _ = await self.driver.execute_query(
            """
            CALL algo.labelPropagation({
                nodeLabels: ['Entity'],
                relationshipTypes: ['RELATES_TO']
            })
            YIELD node, communityId
            WHERE node.group_id = $group_id
            WITH communityId, collect(node.uuid) AS member_uuids
            WHERE $entity_uuid IN member_uuids
            RETURN communityId, member_uuids
            """,
            group_id=entity.group_id,
            entity_uuid=entity.uuid,
        )

        if not records:
            # Entity is isolated
            return ScenarioResult(type=CommunityScenario.NO_COMMUNITY)

        cluster_members = records[0]['member_uuids']

        if len(cluster_members) < self.config.min_cluster_size:
            # Cluster too small
            return ScenarioResult(type=CommunityScenario.NO_COMMUNITY)

        # Find existing communities for cluster members
        community_records, _, _ = await self.driver.execute_query(
            """
            MATCH (c:Community)-[:HAS_MEMBER]->(n:Entity)
            WHERE n.uuid IN $member_uuids
            RETURN DISTINCT c.uuid AS uuid, c.name AS name, c.group_id AS group_id,
                   c.created_at AS created_at, c.summary AS summary
            """,
            member_uuids=cluster_members,
        )

        communities = [get_community_node_from_record(r) for r in community_records]

        if len(communities) == 0:
            # Scenario B: No existing community
            return ScenarioResult(
                type=CommunityScenario.NEW_COMMUNITY,
                cluster_members=cluster_members,
            )

        if len(communities) == 1:
            # Scenario A: Single existing community
            return ScenarioResult(
                type=CommunityScenario.EXISTING_COMMUNITY,
                community=communities[0],
                cluster_members=cluster_members,
            )

        # Scenario C: Multiple communities need to merge
        return ScenarioResult(
            type=CommunityScenario.MERGE_COMMUNITIES,
            communities_to_merge=communities,
            cluster_members=cluster_members,
        )

    async def execute_scenario_a(
        self, new_node: EntityNode, community: CommunityNode
    ) -> CommunityNode:
        """
        Scenario A: Add node to existing community with delta summarization.

        This is the most common case and most efficient - uses O(1) tokens.
        """
        logger.debug(f'Scenario A: Adding {new_node.uuid} to community {community.uuid}')

        # Generate delta summary
        new_summary = await generate_delta_summary(
            self.llm_client,
            existing_summary=community.summary or '',
            new_node=new_node,
        )

        # Update community name if summary changed significantly
        new_name = await generate_summary_description(self.llm_client, new_summary)

        community.summary = new_summary
        community.name = new_name

        # Check if node already has edge to community
        existing_edge_records, _, _ = await self.driver.execute_query(
            """
            MATCH (c:Community {uuid: $community_uuid})-[:HAS_MEMBER]->(n:Entity {uuid: $entity_uuid})
            RETURN count(*) AS count
            """,
            community_uuid=community.uuid,
            entity_uuid=new_node.uuid,
        )

        has_edge = existing_edge_records[0]['count'] > 0 if existing_edge_records else False

        if not has_edge:
            # Create HAS_MEMBER edge
            community_edge = build_community_edges([new_node], community, utc_now())[0]
            await community_edge.save(self.driver)

        # Update embeddings and save
        await community.generate_name_embedding(self.embedder)
        await community.save(self.driver)

        return community

    async def execute_scenario_b(self, cluster: list[EntityNode]) -> CommunityNode:
        """
        Scenario B: Create new community for cluster.

        Uses the existing build_community function which does hierarchical summarization.
        """
        logger.debug(f'Scenario B: Creating new community for {len(cluster)} nodes')

        community_node, community_edges = await build_community(self.llm_client, cluster)

        # Generate and save embeddings
        await community_node.generate_name_embedding(self.embedder)
        await community_node.save(self.driver)

        # Save all edges
        for edge in community_edges:
            await edge.save(self.driver)

        return community_node

    async def execute_scenario_c(
        self, bridging_node: EntityNode, communities: list[CommunityNode]
    ) -> CommunityNode:
        """
        Scenario C: Merge multiple communities into one.

        This is the most complex scenario - we need to:
        1. Merge summaries
        2. Reassign all member edges
        3. Delete the extra communities
        """
        logger.debug(f'Scenario C: Merging {len(communities)} communities via {bridging_node.uuid}')

        if len(communities) < 2:
            raise ValueError('Need at least 2 communities to merge')

        # Keep the first community as the target
        target_community = communities[0]
        communities_to_delete = communities[1:]

        # Merge all summaries into target
        merged_summary = target_community.summary or ''
        for community in communities_to_delete:
            merged_summary = await generate_merge_summary(
                self.llm_client,
                merged_summary,
                community.summary or '',
            )

        target_community.summary = merged_summary
        target_community.name = await generate_summary_description(self.llm_client, merged_summary)

        # Reassign members from deleted communities to target
        for community in communities_to_delete:
            await self.driver.execute_query(
                """
                MATCH (c:Community {uuid: $old_community_uuid})-[r:HAS_MEMBER]->(n:Entity)
                MATCH (target:Community {uuid: $target_community_uuid})
                MERGE (target)-[:HAS_MEMBER]->(n)
                DELETE r
                """,
                old_community_uuid=community.uuid,
                target_community_uuid=target_community.uuid,
            )

            # Delete the old community
            await self.driver.execute_query(
                """
                MATCH (c:Community {uuid: $community_uuid})
                DETACH DELETE c
                """,
                community_uuid=community.uuid,
            )

        # Add bridging node if not already a member
        await self.driver.execute_query(
            """
            MATCH (c:Community {uuid: $community_uuid})
            MATCH (n:Entity {uuid: $entity_uuid})
            MERGE (c)-[:HAS_MEMBER]->(n)
            """,
            community_uuid=target_community.uuid,
            entity_uuid=bridging_node.uuid,
        )

        # Update embeddings and save
        await target_community.generate_name_embedding(self.embedder)
        await target_community.save(self.driver)

        return target_community


# =============================================================================
# New Entry Point for Pipeline Integration
# =============================================================================


async def update_community_incremental(
    driver: GraphDriver,
    llm_client: LLMClient,
    embedder: EmbedderClient,
    entity: EntityNode,
    config: Optional[IncrementalCommunityConfig] = None,
) -> Optional[CommunityNode]:
    """
    Incremental community update entry point for add_episode pipeline.

    This function replaces the old update_community for incremental updates.
    It uses IncrementalCommunityManager to detect scenarios and execute
    the appropriate update strategy.

    Args:
        driver: Graph database driver
        llm_client: LLM client for summarization
        embedder: Embedder client for embeddings
        entity: Entity node to process
        config: Optional configuration

    Returns:
        Updated or created CommunityNode, or None if no action taken
    """
    manager = IncrementalCommunityManager(driver, llm_client, embedder, config)
    return await manager.update_for_entity(entity)


# Kept for backward compatibility with tests, but no longer used in production
class Neighbor(BaseModel):
    node_uuid: str
    edge_count: int


async def get_community_clusters(
    driver: GraphDriver, group_ids: list[str] | None
) -> list[list[EntityNode]]:
    """
    Get community clusters using FalkorDB's native algo.labelPropagation.

    This function runs the native CDLP algorithm on all Entity nodes connected by
    RELATES_TO edges, then filters results by group_id. This is more efficient than
    the previous N+1 query approach because:
    1. CDLP runs once on the entire graph (~300ms for 20K nodes)
    2. Filtering is done in-query rather than in Python loops
    3. Entity fetching is batched per cluster

    Args:
        driver: The graph database driver
        group_ids: Optional list of group_ids to filter. If None, all groups are processed.

    Returns:
        List of clusters, where each cluster is a list of EntityNode objects.
    """
    community_clusters: list[list[EntityNode]] = []

    if group_ids is None:
        group_id_values, _, _ = await driver.execute_query(
            """
            MATCH (n:Entity)
            WHERE n.group_id IS NOT NULL
            RETURN collect(DISTINCT n.group_id) AS group_ids
            """,
        )
        group_ids = group_id_values[0]['group_ids'] if group_id_values else []

    if not group_ids:
        return community_clusters

    for group_id in group_ids:
        records, _, _ = await driver.execute_query(
            """
            CALL algo.labelPropagation({
                nodeLabels: ['Entity'],
                relationshipTypes: ['RELATES_TO']
            })
            YIELD node, communityId
            WHERE node.group_id = $group_id
            WITH communityId, collect(node.uuid) AS member_uuids
            WHERE size(member_uuids) > 1
            RETURN member_uuids
            """,
            group_id=group_id,
        )

        for record in records:
            member_uuids = record['member_uuids']
            if member_uuids:
                nodes = await EntityNode.get_by_uuids(driver, member_uuids)
                if nodes:
                    community_clusters.append(nodes)

    return community_clusters


def label_propagation(projection: dict[str, list[Neighbor]]) -> list[list[str]]:
    """
    Python implementation of label propagation community detection.

    DEPRECATED: This function has a known oscillation bug with symmetric edge weights.
    Use get_community_clusters() which calls FalkorDB's native algo.labelPropagation.

    This implementation is kept for:
    1. Backward compatibility with existing tests
    2. Reference implementation for understanding the algorithm
    3. Fallback if native CDLP is unavailable

    Algorithm:
    1. Start with each node being assigned its own community
    2. Each node will take on the community of the plurality of its neighbors
    3. Ties are broken by going to the largest community
    4. Continue until no communities change during propagation

    Known Issue:
    Synchronous updates can cause infinite oscillation when two nodes have
    equal edge weights to each other. The native FalkorDB implementation
    uses asynchronous updates which avoids this issue.
    """
    if not projection:
        return []

    community_map = {uuid: i for i, uuid in enumerate(projection.keys())}

    while True:
        no_change = True
        new_community_map: dict[str, int] = {}

        for uuid, neighbors in projection.items():
            curr_community = community_map[uuid]

            community_candidates: dict[int, int] = defaultdict(int)
            for neighbor in neighbors:
                community_candidates[community_map[neighbor.node_uuid]] += neighbor.edge_count
            community_lst = [
                (count, community) for community, count in community_candidates.items()
            ]

            community_lst.sort(reverse=True)
            candidate_rank, community_candidate = community_lst[0] if community_lst else (0, -1)
            if community_candidate != -1 and candidate_rank > 1:
                new_community = community_candidate
            else:
                new_community = max(community_candidate, curr_community)

            new_community_map[uuid] = new_community

            if new_community != curr_community:
                no_change = False

        if no_change:
            break

        community_map = new_community_map

    community_cluster_map = defaultdict(list)
    for uuid, community in community_map.items():
        community_cluster_map[community].append(uuid)

    clusters = [cluster for cluster in community_cluster_map.values()]
    return clusters


async def summarize_pair(llm_client: LLMClient, summary_pair: tuple[str, str]) -> str:
    # Prepare context for LLM
    context = {'node_summaries': [{'summary': summary} for summary in summary_pair]}

    llm_response = await llm_client.generate_response(
        prompt_library.summarize_nodes.summarize_pair(context), response_model=Summary
    )

    pair_summary = llm_response.get('summary', '')

    return pair_summary


async def generate_summary_description(llm_client: LLMClient, summary: str) -> str:
    context = {'summary': summary}

    llm_response = await llm_client.generate_response(
        prompt_library.summarize_nodes.summary_description(context),
        response_model=SummaryDescription,
    )

    description = llm_response.get('description', '')

    return description


async def build_community(
    llm_client: LLMClient, community_cluster: list[EntityNode]
) -> tuple[CommunityNode, list[CommunityEdge]]:
    summaries = [entity.summary for entity in community_cluster]
    length = len(summaries)
    while length > 1:
        odd_one_out: str | None = None
        if length % 2 == 1:
            odd_one_out = summaries.pop()
            length -= 1
        new_summaries: list[str] = list(
            await semaphore_gather(
                *[
                    summarize_pair(llm_client, (str(left_summary), str(right_summary)))
                    for left_summary, right_summary in zip(
                        summaries[: int(length / 2)], summaries[int(length / 2) :], strict=False
                    )
                ]
            )
        )
        if odd_one_out is not None:
            new_summaries.append(odd_one_out)
        summaries = new_summaries
        length = len(summaries)

    summary = summaries[0]
    name = await generate_summary_description(llm_client, summary)
    now = utc_now()
    community_node = CommunityNode(
        name=name,
        group_id=community_cluster[0].group_id,
        labels=['Community'],
        created_at=now,
        summary=summary,
    )
    community_edges = build_community_edges(community_cluster, community_node, now)

    logger.debug((community_node, community_edges))

    return community_node, community_edges


async def build_communities(
    driver: GraphDriver, llm_client: LLMClient, group_ids: list[str] | None
) -> tuple[list[CommunityNode], list[CommunityEdge]]:
    community_clusters = await get_community_clusters(driver, group_ids)

    semaphore = asyncio.Semaphore(MAX_COMMUNITY_BUILD_CONCURRENCY)

    async def limited_build_community(cluster):
        async with semaphore:
            return await build_community(llm_client, cluster)

    communities: list[tuple[CommunityNode, list[CommunityEdge]]] = list(
        await semaphore_gather(
            *[limited_build_community(cluster) for cluster in community_clusters]
        )
    )

    community_nodes: list[CommunityNode] = []
    community_edges: list[CommunityEdge] = []
    for community in communities:
        community_nodes.append(community[0])
        community_edges.extend(community[1])

    return community_nodes, community_edges


async def remove_communities(driver: GraphDriver):
    await driver.execute_query(
        """
    MATCH (c:Community)
    DETACH DELETE c
    """,
    )


async def determine_entity_community(
    driver: GraphDriver, entity: EntityNode
) -> tuple[CommunityNode | None, bool]:
    # Check if the node is already part of a community
    records, _, _ = await driver.execute_query(
        """
    MATCH (c:Community)-[:HAS_MEMBER]->(n:Entity {uuid: $entity_uuid})
    RETURN
        c.uuid As uuid, 
        c.name AS name,
        c.group_id AS group_id,
        c.created_at AS created_at, 
        c.summary AS summary
    """,
        entity_uuid=entity.uuid,
    )

    if len(records) > 0:
        return get_community_node_from_record(records[0]), False

    # If the node has no community, add it to the mode community of surrounding entities
    records, _, _ = await driver.execute_query(
        """
    MATCH (c:Community)-[:HAS_MEMBER]->(m:Entity)-[:RELATES_TO]-(n:Entity {uuid: $entity_uuid})
    RETURN
        c.uuid As uuid, 
        c.name AS name,
        c.group_id AS group_id,
        c.created_at AS created_at, 
        c.summary AS summary
    """,
        entity_uuid=entity.uuid,
    )

    communities: list[CommunityNode] = [
        get_community_node_from_record(record) for record in records
    ]

    community_map: dict[str, int] = defaultdict(int)
    for community in communities:
        community_map[community.uuid] += 1

    community_uuid = None
    max_count = 0
    for uuid, count in community_map.items():
        if count > max_count:
            community_uuid = uuid
            max_count = count

    if max_count == 0:
        return None, False

    for community in communities:
        if community.uuid == community_uuid:
            return community, True

    return None, False


async def update_community(
    driver: GraphDriver, llm_client: LLMClient, embedder: EmbedderClient, entity: EntityNode
):
    community, is_new = await determine_entity_community(driver, entity)

    if community is None:
        return

    new_summary = await summarize_pair(llm_client, (entity.summary, community.summary))
    new_name = await generate_summary_description(llm_client, new_summary)

    community.summary = new_summary
    community.name = new_name

    if is_new:
        community_edge = (build_community_edges([entity], community, utc_now()))[0]
        await community_edge.save(driver)

    await community.generate_name_embedding(embedder)

    await community.save(driver)
