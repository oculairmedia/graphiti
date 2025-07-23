// ES Module wrapper for crossfilter2
import './crossfilter2/crossfilter.js';

// The UMD module sets global.crossfilter
const crossfilter = window.crossfilter || self.crossfilter;

// Export as default
export default crossfilter;

// Also export as named export for compatibility
export { crossfilter };