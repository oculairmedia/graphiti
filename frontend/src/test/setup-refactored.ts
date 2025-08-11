// Setup file that enables refactored components for testing
import './setup';

// Enable refactored components globally for tests
beforeAll(() => {
  // Set the localStorage flag to enable refactored components
  localStorage.setItem('graphiti.useRefactoredComponents', 'true');
  console.log('🔧 Refactored components enabled for testing');
});

afterAll(() => {
  // Clean up after tests
  localStorage.removeItem('graphiti.useRefactoredComponents');
});