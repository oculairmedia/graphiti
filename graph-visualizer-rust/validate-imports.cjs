#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

class ImportValidator {
    constructor() {
        this.importMap = {};
        this.errors = [];
        this.warnings = [];
        this.validatedModules = new Set();
        this.moduleGraph = new Map();
    }

    // Load import map from HTML file
    loadImportMap(htmlFile) {
        const content = fs.readFileSync(htmlFile, 'utf8');
        const importMapMatch = content.match(/<script\s+type="importmap"[^>]*>([\s\S]*?)<\/script>/i);
        
        if (importMapMatch) {
            try {
                const importMapJson = importMapMatch[1];
                const parsed = JSON.parse(importMapJson);
                this.importMap = parsed.imports || {};
                console.log(`✓ Loaded import map with ${Object.keys(this.importMap).length} entries`);
            } catch (e) {
                this.errors.push(`Failed to parse import map: ${e.message}`);
            }
        } else {
            this.errors.push('No import map found in HTML file');
        }
    }

    // Extract imports from a JavaScript file
    extractImports(filePath) {
        const content = fs.readFileSync(filePath, 'utf8');
        const imports = [];
        
        // Match various import patterns
        const patterns = [
            // import { x } from 'module'
            /import\s*{[^}]+}\s*from\s*['"]([^'"]+)['"]/g,
            // import x from 'module'
            /import\s+(?!type\s)(\w+)\s+from\s*['"]([^'"]+)['"]/g,
            // import * as x from 'module'
            /import\s*\*\s*as\s*\w+\s*from\s*['"]([^'"]+)['"]/g,
            // import 'module'
            /import\s*['"]([^'"]+)['"]/g,
            // Dynamic imports
            /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g
        ];

        for (const pattern of patterns) {
            let match;
            while ((match = pattern.exec(content)) !== null) {
                const importPath = match[match.length - 1];
                imports.push({
                    path: importPath,
                    line: content.substring(0, match.index).split('\n').length,
                    type: pattern.source.includes('\\*') ? 'namespace' : 
                          pattern.source.includes('{') ? 'named' : 
                          pattern.source.includes('\\(') ? 'dynamic' : 'default'
                });
            }
        }

        return imports;
    }

    // Validate a single import
    validateImport(importData, sourceFile) {
        const { path: importPath, line, type } = importData;
        
        // Skip relative imports and data URLs
        if (importPath.startsWith('.') || importPath.startsWith('/') || importPath.startsWith('data:')) {
            return true;
        }

        // Check if import exists in import map
        if (!this.importMap[importPath]) {
            this.errors.push({
                file: sourceFile,
                line,
                import: importPath,
                type,
                message: `Import "${importPath}" not found in import map`
            });
            return false;
        }

        // Track module dependencies
        if (!this.moduleGraph.has(sourceFile)) {
            this.moduleGraph.set(sourceFile, new Set());
        }
        this.moduleGraph.get(sourceFile).add(importPath);

        return true;
    }

    // Validate wrapper modules
    async validateWrapper(wrapperPath, expectedExports) {
        try {
            const content = fs.readFileSync(wrapperPath, 'utf8');
            
            // Check for common wrapper patterns
            const hasDefaultExport = /export\s+default\s+/m.test(content);
            const hasNamedExport = /export\s*{[^}]+}/m.test(content);
            const hasWindowAssignment = /window\.\w+\s*=/m.test(content);
            const hasSelfAssignment = /self\.\w+\s*=/m.test(content);
            
            if (!hasDefaultExport && !hasNamedExport) {
                this.warnings.push({
                    file: wrapperPath,
                    message: 'Wrapper module has no ES module exports'
                });
            }

            // Check if wrapper properly handles both window and self
            if ((hasWindowAssignment && !hasSelfAssignment) || (!hasWindowAssignment && hasSelfAssignment)) {
                this.warnings.push({
                    file: wrapperPath,
                    message: 'Wrapper should check both window and self for web worker compatibility'
                });
            }

            // Validate import in wrapper
            const wrapperImports = this.extractImports(wrapperPath);
            for (const imp of wrapperImports) {
                // For wrappers, relative imports are expected
                if (!imp.path.startsWith('.') && !imp.path.startsWith('/')) {
                    this.warnings.push({
                        file: wrapperPath,
                        line: imp.line,
                        message: `Wrapper imports non-relative module: ${imp.path}`
                    });
                }
            }

        } catch (e) {
            this.errors.push({
                file: wrapperPath,
                message: `Failed to validate wrapper: ${e.message}`
            });
        }
    }

    // Recursively validate all JavaScript files
    validateDirectory(dir) {
        const files = fs.readdirSync(dir);
        
        for (const file of files) {
            const fullPath = path.join(dir, file);
            const stat = fs.statSync(fullPath);
            
            if (stat.isDirectory() && !file.startsWith('.') && file !== 'node_modules' && file !== 'test' && file !== 'tests' && file !== 'src' && file !== 'lib') {
                this.validateDirectory(fullPath);
            } else if (file.endsWith('.js') && 
                      !file.endsWith('.min.js') && 
                      !file.includes('rollup.config') && 
                      !file.includes('webpack.config') &&
                      !file.includes('build.js') &&
                      !file.includes('test.js') &&
                      !fullPath.includes('/test/') &&
                      !fullPath.includes('/tests/') &&
                      !fullPath.includes('/src/') &&
                      !fullPath.includes('/lib/')) {
                console.log(`Validating ${fullPath}...`);
                
                try {
                    const imports = this.extractImports(fullPath);
                    for (const imp of imports) {
                        this.validateImport(imp, fullPath);
                    }
                    
                    // Special validation for wrapper files
                    if (file.includes('wrapper')) {
                        this.validateWrapper(fullPath);
                    }
                    
                    this.validatedModules.add(fullPath);
                } catch (e) {
                    this.errors.push({
                        file: fullPath,
                        message: `Failed to parse file: ${e.message}`
                    });
                }
            }
        }
    }

    // Generate validation report
    generateReport() {
        console.log('\n' + '='.repeat(80));
        console.log('IMPORT VALIDATION REPORT');
        console.log('='.repeat(80) + '\n');

        console.log(`Total files validated: ${this.validatedModules.size}`);
        console.log(`Total imports in map: ${Object.keys(this.importMap).length}`);
        console.log(`Errors found: ${this.errors.length}`);
        console.log(`Warnings found: ${this.warnings.length}`);

        if (this.errors.length > 0) {
            console.log('\n' + '─'.repeat(80));
            console.log('ERRORS:');
            console.log('─'.repeat(80));
            
            for (const error of this.errors) {
                if (typeof error === 'string') {
                    console.log(`\n❌ ${error}`);
                } else {
                    console.log(`\n❌ ${error.file}`);
                    if (error.line) console.log(`   Line ${error.line}: import "${error.import}"`);
                    console.log(`   ${error.message}`);
                }
            }
        }

        if (this.warnings.length > 0) {
            console.log('\n' + '─'.repeat(80));
            console.log('WARNINGS:');
            console.log('─'.repeat(80));
            
            for (const warning of this.warnings) {
                console.log(`\n⚠️  ${warning.file}`);
                if (warning.line) console.log(`   Line ${warning.line}`);
                console.log(`   ${warning.message}`);
            }
        }

        // Show unused imports from import map
        const usedImports = new Set();
        for (const deps of this.moduleGraph.values()) {
            deps.forEach(dep => usedImports.add(dep));
        }
        
        const unusedImports = Object.keys(this.importMap).filter(imp => !usedImports.has(imp));
        if (unusedImports.length > 0) {
            console.log('\n' + '─'.repeat(80));
            console.log('UNUSED IMPORT MAP ENTRIES:');
            console.log('─'.repeat(80));
            
            for (const unused of unusedImports) {
                console.log(`   ${unused} -> ${this.importMap[unused]}`);
            }
        }

        // Generate dependency graph
        this.generateDependencyGraph();

        return this.errors.length === 0;
    }

    // Generate a simple dependency graph
    generateDependencyGraph() {
        const graphPath = path.join(__dirname, 'import-dependencies.json');
        const graph = {
            nodes: Array.from(this.validatedModules).map(file => ({
                id: file,
                label: path.basename(file)
            })),
            edges: []
        };

        for (const [source, deps] of this.moduleGraph.entries()) {
            for (const dep of deps) {
                graph.edges.push({
                    source,
                    target: dep,
                    label: dep
                });
            }
        }

        fs.writeFileSync(graphPath, JSON.stringify(graph, null, 2));
        console.log(`\n✓ Dependency graph saved to ${graphPath}`);
    }
}

// Main execution
function main() {
    const validator = new ImportValidator();
    
    // Load import map from HTML
    const htmlFile = path.join(__dirname, 'static', 'cosmograph.html');
    validator.loadImportMap(htmlFile);
    
    if (validator.errors.length > 0) {
        validator.generateReport();
        process.exit(1);
    }
    
    // Validate all vendor modules
    const vendorDir = path.join(__dirname, 'static', 'vendor');
    validator.validateDirectory(vendorDir);
    
    // Generate report
    const success = validator.generateReport();
    
    process.exit(success ? 0 : 1);
}

if (require.main === module) {
    main();
}

module.exports = ImportValidator;