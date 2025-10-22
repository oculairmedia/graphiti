import { CosmosInputNode, CosmosInputLink } from '@cosmograph/cosmos';
export type CosmographData<N extends CosmosInputNode = CosmosInputNode, L extends CosmosInputLink = CosmosInputLink> = {
    nodes: N[];
    links: L[];
};
export declare enum FilterType {
    Nodes = "nodes",
    Links = "links"
}
