from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_text_affix_merge_synthetic_probe.py "
            "<pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import execution
    from comfy_extras.nodes_dataset import (
        AddTextPrefixNode,
        AddTextSuffixNode,
        MergeTextListsNode,
        StripWhitespaceNode,
    )
    from comfy_extras.nodes_string import StringConcatenate, StringTrim
    from comfy_extras.nodes_toolkit import CreateList

    targets = (
        AddTextPrefixNode,
        AddTextSuffixNode,
        StripWhitespaceNode,
        MergeTextListsNode,
    )
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
        assert cls.OUTPUT_IS_LIST == [None]
        assert info.get("deprecated", False) is False
        assert cls.is_deprecated is True

    assert AddTextPrefixNode.INPUT_IS_LIST is False
    assert AddTextSuffixNode.INPUT_IS_LIST is False
    assert StripWhitespaceNode.INPUT_IS_LIST is False
    assert MergeTextListsNode.INPUT_IS_LIST is True

    prefix_input = "текст"
    prefix_value = "→ "
    prefix = AddTextPrefixNode.execute(prefix_input, prefix=prefix_value).args[0]
    prefix_wrapped_parameter = AddTextPrefixNode.execute(
        prefix_input, prefix=[prefix_value]
    ).args[0]
    prefix_empty = AddTextPrefixNode.execute(prefix_input, prefix="").args[0]
    assert prefix == [prefix_value + prefix_input]
    assert prefix_wrapped_parameter == prefix
    assert prefix_empty == [prefix_input]

    suffix_value = " ←"
    suffix = AddTextSuffixNode.execute(prefix_input, suffix=suffix_value).args[0]
    suffix_wrapped_parameter = AddTextSuffixNode.execute(
        prefix_input, suffix=[suffix_value]
    ).args[0]
    suffix_empty = AddTextSuffixNode.execute(prefix_input, suffix="").args[0]
    assert suffix == [prefix_input + suffix_value]
    assert suffix_wrapped_parameter == suffix
    assert suffix_empty == [prefix_input]

    whitespace_input = "\u00a0\t текст \n\u2003"
    stripped = StripWhitespaceNode.execute(whitespace_input).args[0]
    internal_whitespace = StripWhitespaceNode.execute("  a \t b  ").args[0]
    whitespace_only = StripWhitespaceNode.execute("\u00a0\t\n\u2003").args[0]
    no_edge_whitespace = StripWhitespaceNode.execute("a b").args[0]
    assert stripped == ["текст"]
    assert internal_whitespace == ["a \t b"]
    assert whitespace_only == [""]
    assert no_edge_whitespace == ["a b"]

    merge_input = ["первый", "", "первый", "третий"]
    merge_node_output = MergeTextListsNode.execute(merge_input)
    merge = merge_node_output.args[0]
    merge_empty = MergeTextListsNode.execute([]).args[0]
    merge_singleton = MergeTextListsNode.execute(["один"]).args[0]
    assert merge == [merge_input]
    assert merge[0] is merge_input
    assert merge_empty == [[]]
    assert merge_singleton == [["один"]]

    create_list = CreateList.execute(
        {"input1": ["первый", ""], "input2": ["первый", "третий"]}
    ).args[0]
    assert create_list == merge_input

    prefix_successor = StringConcatenate.execute(
        prefix_value, prefix_input, ""
    ).args[0]
    suffix_successor = StringConcatenate.execute(
        prefix_input, suffix_value, ""
    ).args[0]
    strip_successor = StringTrim.execute(whitespace_input, "Both").args[0]
    assert prefix_successor == prefix[0]
    assert suffix_successor == suffix[0]
    assert strip_successor == stripped[0]

    merged_prefix = execution.merge_result_data(
        [AddTextPrefixNode.execute("abc", prefix="[").args], AddTextPrefixNode
    )
    merged_suffix = execution.merge_result_data(
        [AddTextSuffixNode.execute("abc", suffix="]").args], AddTextSuffixNode
    )
    merged_strip = execution.merge_result_data(
        [StripWhitespaceNode.execute(" abc ").args], StripWhitespaceNode
    )
    merged_merge = execution.merge_result_data(
        [merge_node_output.args], MergeTextListsNode
    )
    merged_create = execution.merge_result_data(
        [CreateList.execute({"input1": ["a", "b"]}).args], CreateList
    )
    assert merged_prefix == [[["[abc"]]]
    assert merged_suffix == [[["abc]"]]]
    assert merged_strip == [[["abc"]]]
    assert merged_merge == [[[merge_input]]]
    assert merged_create == [["a", "b"]]

    print(
        json.dumps(
            {
                "prefix": {
                    "emptyPrefixIsIdentity": prefix_empty == [prefix_input],
                    "listWrappedParameterUnwrapped": prefix_wrapped_parameter == prefix,
                    "output": prefix,
                    "stringConcatenateParity": prefix_successor == prefix[0],
                },
                "runtimeContract": {
                    "mergedCreateListOutput": merged_create,
                    "mergedMergeTextListsOutput": merged_merge,
                    "mergedPrefixOutput": merged_prefix,
                    "mergedStripOutput": merged_strip,
                    "mergedSuffixOutput": merged_suffix,
                    "schemas": schemas,
                },
                "strip": {
                    "allWhitespaceBecomesEmpty": whitespace_only == [""],
                    "internalWhitespacePreserved": internal_whitespace == ["a \t b"],
                    "noEdgeWhitespaceIsIdentity": no_edge_whitespace == ["a b"],
                    "output": stripped,
                    "stringTrimBothParity": strip_successor == stripped[0],
                },
                "suffix": {
                    "emptySuffixIsIdentity": suffix_empty == [prefix_input],
                    "listWrappedParameterUnwrapped": suffix_wrapped_parameter == suffix,
                    "output": suffix,
                    "stringConcatenateParity": suffix_successor == suffix[0],
                },
                "textList": {
                    "createListEquivalentValues": create_list == merge_input,
                    "emptyOutput": merge_empty,
                    "orderDuplicatesAndEmptyPreserved": merge[0] == merge_input,
                    "passThroughIdentity": merge[0] is merge_input,
                    "singletonOutput": merge_singleton,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
