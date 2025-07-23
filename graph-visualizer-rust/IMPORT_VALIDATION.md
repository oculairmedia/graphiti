# Import Validation System

This project includes a prebuild validation system to catch module resolution errors before runtime.

## Quick Start

```bash
# Run validation
node validate-imports.js

# Build with validation
./build.sh

# Auto-fix common issues
node fix-imports.js
```

## How It Works

1. **validate-imports.js** - Scans all JavaScript files in `static/vendor/` and:
   - Extracts all import statements
   - Checks if each import can be resolved via the import map
   - Validates ES module wrappers
   - Reports unresolved imports with file locations

2. **fix-imports.js** - Automatically fixes common issues:
   - Downloads missing npm packages
   - Creates ES module wrappers for UMD modules
   - Updates the import map in cosmograph.html

3. **build.sh** - Runs validation before building:
   - Ensures all imports are valid
   - Builds Rust application
   - Builds Docker image

## Common Issues

### UMD Modules
Modules like `regl` and `crossfilter2` use UMD format and need ES module wrappers:

```javascript
// Example wrapper for UMD module
import './regl/dist/regl.js';
const regl = window.createREGL;
export default regl;
```

### Missing Dependencies
If validation reports missing modules:
1. Check if it's a runtime dependency (not build tool)
2. Run `node fix-imports.js` to auto-download
3. Or manually: `npm pack module-name && tar -xzf module-name-*.tgz -C static/vendor/module-name --strip-components=1`

### Import Map Updates
Add mappings to `static/cosmograph.html`:
```json
"module-name": "/vendor/module-name/src/index.js",
```

## Ignoring False Positives

Build tool imports (rollup, typescript, etc.) can be safely ignored as they're not needed at runtime.

Focus on fixing imports from actual application code in:
- `/vendor/cosmos/dist/index.js`
- `/vendor/cosmograph/index.js`
- Other runtime modules