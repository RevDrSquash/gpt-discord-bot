import deepeval
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.synthesizer import Synthesizer

from deepeval.synthesizer.config import (
    FiltrationConfig,
    EvolutionConfig,
    StylingConfig,
    ContextConstructionConfig,
)

import src.constants

construction_config = ContextConstructionConfig()
construction_config.chunk_size = 128
construction_config.chunk_overlap = 64

synthesizer = Synthesizer()

synthesizer.generate_goldens_from_docs(
    document_paths=[
		'test/character creation summary.txt', 
		'test/grapples.txt', 
		'test/instill action.txt', 
		'test/lore.txt', 
		'test/resolving a decisive attack.txt',
		'test/resolving a withering attack.txt',
		'test/sorcerous motes and the shape sorcery action.txt',
	],
    include_expected_output=True,
    context_construction_config=construction_config,
)

print(synthesizer.synthetic_goldens)


