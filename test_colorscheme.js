// Test script to inspect colorScheme in localStorage
// Run this in browser console after making changes

console.log('=== Testing colorScheme persistence ===');

// Check localStorage
const configKey = 'graphiti.config.v1';
const storedConfig = localStorage.getItem(configKey);

if (storedConfig) {
    try {
        const parsed = JSON.parse(storedConfig);
        console.log('Stored config found:', parsed);
        console.log('ColorScheme in stored config:', parsed.graphConfig?.colorScheme);
    } catch (e) {
        console.error('Failed to parse stored config:', e);
    }
} else {
    console.log('No stored config found');
}

// Show all graphiti keys
const graphitiKeys = Object.keys(localStorage).filter(k => k.includes('graphiti'));
console.log('All graphiti localStorage keys:', graphitiKeys);

graphitiKeys.forEach(key => {
    const value = localStorage.getItem(key);
    console.log(`${key}:`, value);
});