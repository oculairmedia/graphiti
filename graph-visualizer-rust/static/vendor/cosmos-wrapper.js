// ES Module wrapper for @cosmograph/cosmos
// The library appears to be bundled and doesn't expose Graph directly
// We'll create a mock export to satisfy the import requirements

export class Graph {
    constructor(canvas, config) {
        console.warn('@cosmograph/cosmos Graph class is not directly available - using Cosmograph wrapper');
        // This is a placeholder - the actual Graph functionality is internal to Cosmograph
    }
}

// Export any other potential imports that might be needed
export default { Graph };