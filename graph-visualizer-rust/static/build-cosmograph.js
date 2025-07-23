// This is a build script to bundle Cosmograph for local use
// Run this with Node.js to create a bundled version

const fs = require('fs');
const https = require('https');

console.log('Downloading Cosmograph...');

// Download the Cosmograph package
const packageUrl = 'https://registry.npmjs.org/@cosmograph/cosmograph/-/cosmograph-1.4.2.tgz';

https.get(packageUrl, (response) => {
    const chunks = [];
    
    response.on('data', (chunk) => {
        chunks.push(chunk);
    });
    
    response.on('end', () => {
        const buffer = Buffer.concat(chunks);
        fs.writeFileSync('cosmograph.tgz', buffer);
        console.log('Downloaded Cosmograph package');
        
        // Extract and process the package
        const { execSync } = require('child_process');
        
        try {
            execSync('tar -xzf cosmograph.tgz');
            execSync('cp -r package/dist/* .');
            console.log('Extracted Cosmograph files');
            
            // Create a simple wrapper
            const wrapper = `
// Cosmograph bundled for local use
import * as Cosmograph from './index.js';
window.Cosmograph = Cosmograph;
export * from './index.js';
`;
            fs.writeFileSync('cosmograph-bundle.js', wrapper);
            console.log('Created bundle wrapper');
            
        } catch (error) {
            console.error('Error processing package:', error);
        }
    });
}).on('error', (error) => {
    console.error('Download error:', error);
});