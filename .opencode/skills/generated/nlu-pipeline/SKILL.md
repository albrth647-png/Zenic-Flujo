---
name: nlu-pipeline
description: NLU/ML pipeline - intent classification, entity extraction, language processing
load: on-demand
tokens: ~160
---

# NLU Pipeline

## Module: `src/nlu/` (32 files)
Natural Language Understanding pipeline for intent classification and entity extraction.

### Key Components
- **Intent Classifier**: ML-based intent recognition (scikit-learn)
- **Entity Extractor**: Named entity recognition
- **Language Detector**: Multi-language support
- **Training Pipeline**: Model training and evaluation
- **Context Manager**: Conversation context tracking

### Stack
- scikit-learn for ML models
- OpenAI API for advanced NLU
- Custom tokenizer and vectorizer

### Usage
```python
from src.nlu import NLUPipeline
nlu = NLUPipeline()
result = nlu.process("crear factura para cliente 123")
# intent="create_invoice", entities={"client_id": 123}
```

### Key Files
- `src/nlu/classifier.py` - Intent classification
- `src/nlu/entities.py` - Entity extraction
- `src/nlu/train.py` - Model training
