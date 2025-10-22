# Cerebras Temperature Optimization Results

## Objective
Optimize the temperature hyperparameter for qwen-3-coder-480b to improve entity extraction success rate and quality.

## Test Configuration
- **Model**: qwen-3-coder-480b
- **Temperatures Tested**: [0.0, 0.1, 0.2, 0.3, 0.5]
- **Test Episodes**: 2 (tech_meeting, product_launch)
- **Structured Output**: JSON schema with strict validation
- **Metrics**: Entity F1, Relationship F1, Response Time, Success Rate

## Results Summary

| Temperature | Entity F1 | Relationship F1 | Total F1 | Avg Time | Success Rate |
|-------------|-----------|-----------------|----------|----------|--------------|
| **0.0** ✅ | **74.51%** | **51.67%** | **63.09%** | **0.71s** | **100%** |
| **0.1** ✅ | **74.51%** | **51.67%** | **63.09%** | **0.71s** | **100%** |
| 0.2 | 74.51% | 41.43% | 57.97% | 2.13s | 100% |
| 0.3 | 74.51% | 41.43% | 57.97% | 1.36s | 100% |
| 0.5 | 72.22% | 39.23% | 55.73% | 1.64s | 100% |

## Key Findings

### 1. Temperature 0.0 is Optimal
- **Best overall F1 score**: 63.09%
- **Best relationship extraction**: 51.67% F1
- **Fastest response time**: 0.71s average
- **100% success rate** with deterministic output

### 2. Temperature 0.1 Performs Identically
- Identical metrics to temperature 0.0
- Shows qwen-3-coder-480b is highly deterministic at low temperatures

### 3. Higher Temperatures Degrade Performance
- **Temperature 0.2+**: Relationship F1 drops to ~41%
- **Temperature 0.5**: Entity F1 drops to 72.22%
- **Response times become inconsistent** (0.5s to 3.7s range)

### 4. Entity vs Relationship Extraction
- **Entity extraction** remains stable (72-75% F1) across temperatures
- **Relationship extraction** is more sensitive to temperature
- Structured output schema helps maintain consistency

## Production Recommendation

### ✅ **Keep Current Setting: Temperature = 0.0**

**Rationale:**
1. **Optimal Quality**: Highest total F1 score (63.09%)
2. **Deterministic**: Consistent results for production reliability
3. **Fast Response**: Best average response time (0.71s)
4. **Already Configured**: `DEFAULT_TEMPERATURE = 0` in config.py

### No Changes Required
The current production configuration is already optimal:
```python
# graphiti_core/llm_client/config.py
DEFAULT_TEMPERATURE = 0  # ✅ Optimal setting
```

## Next Steps for Further Optimization

Since temperature 0.0 is optimal, consider testing other hyperparameters:

### 1. **Top-p Optimization** (Current: 0.8)
Test values: [0.7, 0.8, 0.9, 1.0] with temperature=0.0

### 2. **Max Tokens Optimization** (Current: 8192)
Test values: [1000, 2000, 4000] for faster responses

### 3. **System Prompt Engineering**
- Add more specific entity type guidance
- Include few-shot examples
- Optimize relationship extraction instructions

### 4. **Schema Refinement**
- Add entity type enums (person, organization, location)
- Include confidence thresholds
- Optimize required vs optional fields

## Conclusion

**The current temperature setting (0.0) is optimal for qwen-3-coder-480b**. No configuration changes are needed. Focus future optimization efforts on prompt engineering, schema refinement, and other hyperparameters like top_p.

---
*Test Date: August 30, 2025*  
*Model: qwen-3-coder-480b*  
*Test File: test_cerebras_temp_simple.py*