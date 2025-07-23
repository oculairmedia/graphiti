// ES Module wrapper for regl
// Since regl is a UMD module that expects to run in global context,
// we'll load it as a script and then export the result

// Check if regl is already loaded
if (!window.createREGL) {
    // Create a promise that resolves when regl is loaded
    window.__reglLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/vendor/regl/dist/regl.js';
        script.onload = () => {
            if (window.createREGL) {
                resolve(window.createREGL);
            } else {
                reject(new Error('regl loaded but createREGL not found'));
            }
        };
        script.onerror = () => reject(new Error('Failed to load regl'));
        document.head.appendChild(script);
    });
}

// Wait for regl to load
const createREGL = await (window.__reglLoadPromise || Promise.resolve(window.createREGL));

// Export as default
export default createREGL;

// Also export as named exports
export { createREGL, createREGL as regl };