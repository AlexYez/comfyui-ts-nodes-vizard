"""Keep historical ten-section fixtures separate from the new authored format."""
import re
from tools import catalog
from tools.october_content import CORE
from tools.november_content import CORE as NOVEMBER


def expected_sections(article):
    node = article["runtimeIdentity"]["classType"]
    if node in NOVEMBER:
        evidence = catalog.load_json(catalog.CONTENT / "research/november-2026-update.json")
        return len(re.findall(r"^## ", NOVEMBER[node][1], re.M)) + 3 + bool(evidence["coreArticles"][node]["workflowOccurrences"])
    if node not in CORE:
        return 10
    evidence = catalog.load_json(catalog.CONTENT / "research/october-2026-update.json")
    # Authored headings + inputs + outputs + sources, and a cases section when
    # saved examples exist. No fixed ten-section requirement for new prose.
    return len(re.findall(r"^## ", CORE[node][1], re.M)) + 3 + bool(evidence["officialWorkflowOccurrences"][node])
