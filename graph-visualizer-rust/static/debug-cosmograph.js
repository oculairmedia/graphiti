// Debug script for testing Cosmograph node click functionality
console.log('=== Cosmograph Debug Script Loaded ===');

// Wait for cosmograph to be initialized
setTimeout(() => {
    if (window.cosmographInstance) {
        console.log('✓ Cosmograph instance found');
        
        // Check config
        console.log('Config onClick:', window.cosmographInstance.config?.onClick ? 'defined' : 'undefined');
        
        // Try to get nodes
        const nodeCount = window.cosmographInstance.getNodeCount?.();
        console.log('Node count:', nodeCount);
        
        // Add global debug function
        window.debugCosmograph = {
            selectFirst: () => {
                console.log('Selecting first node...');
                window.cosmographInstance.selectNodeByIndex(0);
                const selected = window.cosmographInstance.getSelectedNodes();
                console.log('Selected nodes:', selected);
                return selected;
            },
            
            testClick: (x, y) => {
                console.log(`Simulating click at ${x}, ${y}`);
                const event = new MouseEvent('click', {
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: x,
                    clientY: y
                });
                document.getElementById('graphCanvas').dispatchEvent(event);
            },
            
            showNodeData: () => {
                console.log('Node data map size:', window.nodeDataMap?.size || 0);
                if (window.nodeDataMap && window.nodeDataMap.size > 0) {
                    const firstEntry = window.nodeDataMap.entries().next().value;
                    console.log('Sample node data:', firstEntry);
                }
            },
            
            getConfig: () => {
                return window.cosmographInstance.config;
            }
        };
        
        console.log('Debug functions available:');
        console.log('- debugCosmograph.selectFirst()');
        console.log('- debugCosmograph.testClick(x, y)');
        console.log('- debugCosmograph.showNodeData()');
        console.log('- debugCosmograph.getConfig()');
        
    } else {
        console.log('✗ Cosmograph instance not found');
    }
}, 1000);