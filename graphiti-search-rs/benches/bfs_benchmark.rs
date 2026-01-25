use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use std::collections::HashMap;

use graphiti_search_rs::search::bfs::{
    BfsConfig, _calculate_shortest_paths, _find_nodes_within_distance,
};

fn create_test_graph(node_count: usize, avg_degree: usize) -> HashMap<String, Vec<String>> {
    let mut adjacency = HashMap::new();

    for i in 0..node_count {
        let node_id = format!("node_{}", i);
        let mut neighbors = Vec::new();

        for j in 0..avg_degree {
            let neighbor_idx = (i + j + 1) % node_count;
            neighbors.push(format!("node_{}", neighbor_idx));
        }

        adjacency.insert(node_id, neighbors);
    }

    adjacency
}

fn create_hub_graph(node_count: usize, hub_degree: usize) -> HashMap<String, Vec<String>> {
    let mut adjacency = HashMap::new();

    let mut hub_neighbors = Vec::new();
    for i in 1..node_count {
        hub_neighbors.push(format!("node_{}", i));
        adjacency.insert(format!("node_{}", i), vec!["node_0".to_string()]);
    }
    hub_neighbors.truncate(hub_degree);
    adjacency.insert("node_0".to_string(), hub_neighbors);

    adjacency
}

fn bench_shortest_paths(c: &mut Criterion) {
    let mut group = c.benchmark_group("BFS Shortest Paths");

    for size in [100, 500, 1000, 5000].iter() {
        let graph = create_test_graph(*size, 5);

        group.throughput(Throughput::Elements(*size as u64));
        group.bench_with_input(BenchmarkId::from_parameter(size), &graph, |b, graph| {
            b.iter(|| _calculate_shortest_paths(graph, "node_0"));
        });
    }

    group.finish();
}

fn bench_nodes_within_distance(c: &mut Criterion) {
    let mut group = c.benchmark_group("BFS Nodes Within Distance");

    let graph = create_test_graph(1000, 5);

    for depth in [1, 2, 3, 4, 5].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(depth), depth, |b, &depth| {
            b.iter(|| _find_nodes_within_distance(&graph, &["node_0".to_string()], depth));
        });
    }

    group.finish();
}

fn bench_hub_graph_traversal(c: &mut Criterion) {
    let mut group = c.benchmark_group("BFS Hub Graph");

    for hub_degree in [50, 100, 200, 500].iter() {
        let graph = create_hub_graph(1000, *hub_degree);

        group.bench_with_input(
            BenchmarkId::from_parameter(hub_degree),
            &graph,
            |b, graph| {
                b.iter(|| _calculate_shortest_paths(graph, "node_0"));
            },
        );
    }

    group.finish();
}

fn bench_bfs_config_creation(c: &mut Criterion) {
    c.bench_function("BfsConfig::default", |b| {
        b.iter(|| BfsConfig::default());
    });
}

criterion_group!(
    benches,
    bench_shortest_paths,
    bench_nodes_within_distance,
    bench_hub_graph_traversal,
    bench_bfs_config_creation,
);

criterion_main!(benches);
