# whyLayer Prompts
from .ayanokouji_base import AYANOKOUJI_SYSTEM_PROMPT, PersonaConfig
from .interrogation import (
    INITIAL_QUESTIONS_PROMPT,
    NEXT_QUESTION_PROMPT,
    PHASES,
    get_phase,
    format_history,
)
from .classification import CLASSIFICATION_PROMPT
from .verdict import VERDICT_PROMPT
