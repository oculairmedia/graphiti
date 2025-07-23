#!/usr/bin/env node

import { readFileSync, readdirSync, statSync } from 'fs';
import { join, relative } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ANSI color codes
const RED = '\x1b[31m';
const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const BLUE = '\x1b[34m';
const RESET = '\x1b[0m';

// Read the import map from cosmograph.html
function getImportMap() {
    const htmlPath = join(__dirname, 'static', 'cosmograph.html');
    const html = readFileSync(htmlPath, 'utf-8');
    
    // Extract import map
    const importMapMatch = html.match(/<script type="importmap">([\s\S]*?)<\/script>/);
    if (!importMapMatch) {
        throw new Error('Could not find import map in cosmograph.html');
    }
    
    try {
        const importMapJson = importMapMatch[1];
        const importMap = JSON.parse(importMapJson);
        return importMap.imports || {};
    } catch (e) {
        throw new Error(`Failed to parse import map: ${e.message}`);
    }
}

// Extract imports from JavaScript file
function extractImports(filePath) {
    const content = readFileSync(filePath, 'utf-8');
    const imports = new Set();
    
    // Match various import patterns
    const patterns = [
        // import defaultExport from 'module'
        /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]/g,
        // import { named } from 'module'
        /import\s*\{[^}]+\}\s*from\s+['"]([^'"]+)['"]/g,
        // import * as name from 'module'
        /import\s*\*\s*as\s+\w+\s+from\s+['"]([^'"]+)['"]/g,
        // import 'module'
        /import\s+['"]([^'"]+)['"]/g,
        // dynamic import()
        /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g
    ];
    
    for (const pattern of patterns) {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            // Extract the module specifier (last capture group)
            const moduleSpecifier = match[match.length - 1];
            if (moduleSpecifier) {
                imports.add(moduleSpecifier);
            }
        }
    }
    
    return Array.from(imports);
}

// Get all JavaScript files in vendor directory
function getAllJsFiles(dir, files = []) {
    const entries = readdirSync(dir);
    
    for (const entry of entries) {
        const fullPath = join(dir, entry);
        const stat = statSync(fullPath);
        
        if (stat.isDirectory()) {
            // Skip node_modules and hidden directories
            if (!entry.startsWith('.') && entry !== 'node_modules') {
                getAllJsFiles(fullPath, files);
            }
        } else if (entry.endsWith('.js') || entry.endsWith('.mjs')) {
            files.push(fullPath);
        }
    }
    
    return files;
}

// Check if import can be resolved
function canResolveImport(importSpecifier, importMap, currentFilePath) {
    // Relative imports
    if (importSpecifier.startsWith('./') || importSpecifier.startsWith('../')) {
        return { resolved: true, type: 'relative' };
    }
    
    // Absolute paths
    if (importSpecifier.startsWith('/')) {
        return { resolved: true, type: 'absolute' };
    }
    
    // Check import map
    if (importMap[importSpecifier]) {
        return { resolved: true, type: 'mapped', mapping: importMap[importSpecifier] };
    }
    
    // Check for partial matches (e.g., 'd3-color' might map to 'd3-color/src/index.js')
    for (const [key, value] of Object.entries(importMap)) {
        if (importSpecifier.startsWith(key + '/')) {
            return { resolved: true, type: 'partial-mapped', mapping: value };
        }
    }
    
    return { resolved: false, type: 'unmapped' };
}

// Validate wrapper modules
async function validateWrapper(wrapperPath, importMap) {
    const issues = [];
    
    try {
        // Dynamic import to check if module loads
        const module = await import(fileURLToPath(new URL(`file://${wrapperPath}`)));
        
        // Check for default export
        if (!module.default && !module.__moduleExports) {
            issues.push({
                type: 'missing-default',
                message: 'Wrapper module does not provide a default export'
            });
        }
        
        // Check if the wrapped module name is in import map
        const wrapperName = Object.keys(importMap).find(key => 
            importMap[key].includes(wrapperPath.split('/').pop())
        );
        
        if (wrapperName) {
            console.log(`${GREEN}✓${RESET} Wrapper ${wrapperName} exports: ${Object.keys(module).join(', ')}`);
        }
    } catch (e) {
        issues.push({
            type: 'load-error',
            message: `Failed to load wrapper: ${e.message}`
        });
    }
    
    return issues;
}

// Main validation function
async function validateImports() {
    console.log(`${BLUE}Module Import Validator${RESET}\n`);
    
    try {
        // Get import map
        const importMap = getImportMap();
        console.log(`${GREEN}✓${RESET} Found import map with ${Object.keys(importMap).length} mappings\n`);
        
        // Get all JS files
        const vendorDir = join(__dirname, 'static', 'vendor');
        const jsFiles = getAllJsFiles(vendorDir);
        console.log(`${GREEN}✓${RESET} Found ${jsFiles.length} JavaScript files to analyze\n`);
        
        let totalImports = 0;
        let unresolvedImports = [];
        let wrapperIssues = [];
        
        // Check each file
        for (const filePath of jsFiles) {
            const relativePath = relative(__dirname, filePath);
            const imports = extractImports(filePath);
            
            if (imports.length > 0) {
                console.log(`${BLUE}${relativePath}:${RESET}`);
                
                for (const importSpec of imports) {
                    totalImports++;
                    const resolution = canResolveImport(importSpec, importMap, filePath);
                    
                    if (resolution.resolved) {
                        console.log(`  ${GREEN}✓${RESET} ${importSpec} (${resolution.type})`);
                        if (resolution.mapping) {
                            console.log(`    → ${resolution.mapping}`);
                        }
                    } else {
                        console.log(`  ${RED}✗${RESET} ${importSpec} (${resolution.type})`);
                        unresolvedImports.push({
                            file: relativePath,
                            import: importSpec,
                            line: getLineNumber(filePath, importSpec)
                        });
                    }
                }
                console.log('');
            }
            
            // Check wrapper modules
            if (filePath.includes('-wrapper.js') || filePath.includes('-es-wrapper.js')) {
                const issues = await validateWrapper(filePath, importMap);
                if (issues.length > 0) {
                    wrapperIssues.push({ file: relativePath, issues });
                }
            }
        }
        
        // Summary
        console.log(`${BLUE}Summary:${RESET}`);
        console.log(`  Total imports analyzed: ${totalImports}`);
        console.log(`  Resolved imports: ${GREEN}${totalImports - unresolvedImports.length}${RESET}`);
        console.log(`  Unresolved imports: ${RED}${unresolvedImports.length}${RESET}\n`);
        
        if (unresolvedImports.length > 0) {
            console.log(`${RED}Unresolved imports:${RESET}`);
            for (const unresolved of unresolvedImports) {
                console.log(`  ${unresolved.file}:${unresolved.line} - ${unresolved.import}`);
            }
            console.log('');
        }
        
        if (wrapperIssues.length > 0) {
            console.log(`${YELLOW}Wrapper module issues:${RESET}`);
            for (const wrapper of wrapperIssues) {
                console.log(`  ${wrapper.file}:`);
                for (const issue of wrapper.issues) {
                    console.log(`    ${RED}✗${RESET} ${issue.type}: ${issue.message}`);
                }
            }
            console.log('');
        }
        
        // Generate suggestions
        if (unresolvedImports.length > 0) {
            console.log(`${YELLOW}Suggestions:${RESET}`);
            const uniqueImports = [...new Set(unresolvedImports.map(u => u.import))];
            
            for (const imp of uniqueImports) {
                console.log(`\nAdd to import map in cosmograph.html:`);
                console.log(`  "${imp}": "/vendor/${imp}/src/index.js",`);
            }
        }
        
        // Exit with error if there are unresolved imports
        if (unresolvedImports.length > 0 || wrapperIssues.length > 0) {
            process.exit(1);
        } else {
            console.log(`\n${GREEN}✓ All imports validated successfully!${RESET}`);
        }
        
    } catch (error) {
        console.error(`${RED}Error: ${error.message}${RESET}`);
        process.exit(1);
    }
}

// Helper to get line number of import
function getLineNumber(filePath, importSpec) {
    const content = readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes(importSpec)) {
            return i + 1;
        }
    }
    
    return '?';
}

// Run validation
validateImports();