from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_text_transform_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import execution
    from comfy_extras.nodes_dataset import (
        ReplaceTextNode,
        TextToLowercaseNode,
        TextToUppercaseNode,
        TruncateTextNode,
    )
    from comfy_extras.nodes_string import CaseConverter, StringReplace

    targets = [
        TextToLowercaseNode,
        TextToUppercaseNode,
        TruncateTextNode,
        ReplaceTextNode,
    ]
    schemas = {}
    for cls in targets:
        cls.VALIDATE_CLASS()
        info = cls.GET_NODE_INFO_V1()
        schemas[cls.node_id] = {
            "inputIsList": cls.INPUT_IS_LIST,
            "outputIsList": cls.OUTPUT_IS_LIST,
            "runtimeDeprecated": info.get("deprecated", False),
            "sourceDeprecated": cls.is_deprecated,
        }
        assert cls.INPUT_IS_LIST is False
        assert cls.OUTPUT_IS_LIST == [None]
        assert info.get("deprecated", False) is False
        expected_source_deprecated = cls is not TruncateTextNode
        assert cls.is_deprecated is expected_source_deprecated

    lower_input = "ПрИВЕТ İ Σ ẞ"
    lower = TextToLowercaseNode.execute(lower_input).args[0]
    assert lower == [lower_input.lower()]
    assert lower == ["привет i̇ σ ß"]

    upper_input = "straße ı σς"
    upper = TextToUppercaseNode.execute(upper_input).args[0]
    assert upper == [upper_input.upper()]
    assert upper == ["STRASSE I ΣΣ"]

    decomposed = "A😀e\u0301Б"
    truncated = TruncateTextNode.execute(decomposed, max_length=4).args[0]
    assert truncated == [decomposed[:4]]
    assert truncated == ["A😀e\u0301"]
    assert TruncateTextNode.execute("abc", max_length=77).args[0] == ["abc"]
    assert TruncateTextNode.execute("😀😀", max_length=[1]).args[0] == ["😀"]

    overlap = ReplaceTextNode.execute("aaaa", find="aa", replace="b").args[0]
    empty_find = ReplaceTextNode.execute("abc", find="", replace="-").args[0]
    case_sensitive = ReplaceTextNode.execute("AbA", find="a", replace="x").args[0]
    deleted = ReplaceTextNode.execute("one two one", find="one", replace="").args[0]
    list_params = ReplaceTextNode.execute(
        "a-a", find=["a"], replace=["A"]
    ).args[0]
    assert overlap == ["bb"]
    assert empty_find == ["-a-b-c-"]
    assert case_sensitive == ["AbA"]
    assert deleted == [" two "]
    assert list_params == ["A-A"]

    lower_output = TextToLowercaseNode.execute("ABC")
    merged = execution.merge_result_data([lower_output.args], TextToLowercaseNode)
    assert merged == [[['abc']]]
    chained_direct_error = None
    try:
        TextToUppercaseNode.execute(merged[0][0])
    except AttributeError as exc:
        chained_direct_error = type(exc).__name__
    assert chained_direct_error == "AttributeError"

    case_lower = CaseConverter.execute(lower_input, "lowercase").args[0]
    case_upper = CaseConverter.execute(upper_input, "UPPERCASE").args[0]
    string_replace = StringReplace.execute("aaaa", "aa", "b").args[0]
    assert case_lower == lower_input.lower()
    assert case_upper == upper_input.upper()
    assert string_replace == "bb"

    print(
        json.dumps(
            {
                "caseConversion": {
                    "lowerInput": lower_input,
                    "lowerOutput": lower,
                    "upperInput": upper_input,
                    "upperOutput": upper,
                    "caseConverterParity": {
                        "lowercase": case_lower == lower[0],
                        "uppercase": case_upper == upper[0],
                    },
                },
                "replace": {
                    "caseSensitive": case_sensitive,
                    "deleteMatches": deleted,
                    "emptyFind": empty_find,
                    "listWrappedParametersUnwrapped": list_params,
                    "nonOverlapping": overlap,
                    "stringReplaceParity": string_replace == overlap[0],
                },
                "runtimeContract": {
                    "directChainingFailsFromNestedOutput": chained_direct_error,
                    "mergedLowerOutput": merged,
                    "schemas": schemas,
                },
                "truncate": {
                    "decomposedInput": decomposed,
                    "maxLength4": truncated,
                    "shortInputUnchanged": True,
                    "unicodeCodePointSlice": True,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
