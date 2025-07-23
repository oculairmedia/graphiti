#!/usr/bin/env node

import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { join } from 'path';
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

async function validateRuntime() {
    console.log(`${BLUE}Runtime Module Validation${RESET}\n`);
    console.log('Starting headless browser to test module loading...\n');
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    
    // Collect console errors
    const errors = [];
    const warnings = [];
    
    page.on('console', msg => {
        if (msg.type() === 'error') {
            errors.push(msg.text());
        } else if (msg.type() === 'warning') {
            warnings.push(msg.text());
        }
    });
    
    page.on('pageerror', error => {
        errors.push(error.toString());
    });
    
    try {
        // Start local server or use existing one
        const baseUrl = 'http://localhost:3000';
        
        // Test cosmograph page
        console.log(`${BLUE}Testing Cosmograph page...${RESET}`);
        await page.goto(`${baseUrl}/cosmograph`, { waitUntil: 'networkidle' });
        
        // Wait a bit for async imports
        await page.waitForTimeout(3000);
        
        // Check if key modules loaded
        const moduleChecks = await page.evaluate(() => {
            const checks = {
                regl: typeof window.createREGL !== 'undefined',
                cosmograph: false,
                d3: false
            };
            
            // Check if modules are available
            return new Promise((resolve) => {
                // Try to import and check modules
                import('@cosmograph/cosmograph').then(module => {
                    checks.cosmograph = module.Cosmograph !== undefined;
                    
                    import('d3-selection').then(d3Module => {
                        checks.d3 = d3Module.select !== undefined;
                        resolve(checks);
                    }).catch(() => {
                        resolve(checks);
                    });
                }).catch(() => {
                    resolve(checks);
                });
            });
        });
        
        // Report results
        console.log(`\n${BLUE}Module Loading Results:${RESET}`);
        for (const [module, loaded] of Object.entries(moduleChecks)) {
            if (loaded) {
                console.log(`  ${GREEN}✓${RESET} ${module}`);
            } else {
                console.log(`  ${RED}✗${RESET} ${module}`);
            }
        }
        
        if (errors.length > 0) {
            console.log(`\n${RED}Runtime Errors:${RESET}`);
            errors.forEach(error => {
                console.log(`  ${RED}✗${RESET} ${error}`);
            });
        }
        
        if (warnings.length > 0) {
            console.log(`\n${YELLOW}Warnings:${RESET}`);
            warnings.forEach(warning => {
                console.log(`  ${YELLOW}⚠${RESET} ${warning}`);
            });
        }
        
        // Test specific wrapper modules
        console.log(`\n${BLUE}Testing Wrapper Modules:${RESET}`);
        
        const wrapperTests = [
            { name: 'regl-wrapper', path: '/vendor/regl-wrapper.js', exportName: 'default' },
            { name: 'crossfilter2-wrapper', path: '/vendor/crossfilter2-es-wrapper.js', exportName: 'default' }
        ];
        
        for (const wrapper of wrapperTests) {
            try {
                const result = await page.evaluate(async (wrapper) => {
                    try {
                        const module = await import(wrapper.path);
                        return {
                            success: true,
                            hasExport: module[wrapper.exportName] !== undefined,
                            exportType: typeof module[wrapper.exportName]
                        };
                    } catch (e) {
                        return {
                            success: false,
                            error: e.toString()
                        };
                    }
                }, wrapper);
                
                if (result.success && result.hasExport) {
                    console.log(`  ${GREEN}✓${RESET} ${wrapper.name} (exports ${wrapper.exportName}: ${result.exportType})`);
                } else if (result.success) {
                    console.log(`  ${YELLOW}⚠${RESET} ${wrapper.name} (missing ${wrapper.exportName} export)`);
                } else {
                    console.log(`  ${RED}✗${RESET} ${wrapper.name} - ${result.error}`);
                }
            } catch (e) {
                console.log(`  ${RED}✗${RESET} ${wrapper.name} - ${e.message}`);
            }
        }
        
        // Summary
        const hasErrors = errors.length > 0 || !Object.values(moduleChecks).every(v => v);
        
        console.log(`\n${BLUE}Summary:${RESET}`);
        if (hasErrors) {
            console.log(`${RED}✗ Runtime validation failed${RESET}`);
            process.exit(1);
        } else {
            console.log(`${GREEN}✓ All modules loaded successfully!${RESET}`);
        }
        
    } catch (error) {
        console.error(`${RED}Validation error: ${error.message}${RESET}`);
        process.exit(1);
    } finally {
        await browser.close();
    }
}

// Check if playwright is installed
try {
    await import('playwright');
} catch (e) {
    console.error(`${RED}Error: Playwright not installed${RESET}`);
    console.log('\nTo use runtime validation, install playwright:');
    console.log('  npm install --save-dev playwright');
    console.log('\nThen run: npx playwright install chromium');
    process.exit(1);
}

// Run validation
validateRuntime();