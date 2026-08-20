import type {
  CatalogArticle,
  LocaleCode,
  RuntimeNodeDefinition
} from "../types/contracts";

function escapeMarkdown(value: string): string {
  return value.replace(/[\\`*_[\]<>#|]/g, "\\$&");
}

function portsTable(
  ports: RuntimeNodeDefinition["inputs"],
  locale: LocaleCode
): string {
  if (ports.length === 0) {
    return locale === "ru" ? "_Нет объявленных портов._" : "_No declared ports._";
  }
  const optional = locale === "ru" ? "Необязательный" : "Optional";
  const yes = locale === "ru" ? "да" : "yes";
  const no = locale === "ru" ? "нет" : "no";
  return [
    `| ${locale === "ru" ? "Имя" : "Name"} | ${
      locale === "ru" ? "Тип" : "Type"
    } | ${optional} |`,
    "| --- | --- | --- |",
    ...ports.map(
      (port) =>
        `| ${escapeMarkdown(port.name)} | ${escapeMarkdown(port.type)} | ${
          port.optional ? yes : no
        } |`
    )
  ].join("\n");
}

export function createMissingArticle(
  classType: string,
  runtime: RuntimeNodeDefinition | undefined,
  locale: LocaleCode
): CatalogArticle {
  const ru = locale === "ru";
  const title = runtime?.displayName || classType;
  const body = runtime
    ? [
        `# ${escapeMarkdown(title)}`,
        "",
        runtime.description ||
          (ru
            ? "Описание пока отсутствует в данных ComfyUI."
            : "The ComfyUI definition does not provide a description yet."),
        "",
        `- **${ru ? "Системное имя" : "Class type"}: \`${escapeMarkdown(classType)}\``,
        `- **${ru ? "Категория" : "Category"}: ${escapeMarkdown(runtime.category)}`,
        ...(runtime.pythonModule
          ? [
              `- **${ru ? "Python-модуль" : "Python module"}: \`${escapeMarkdown(
                runtime.pythonModule
              )}\``
            ]
          : []),
        "",
        `## ${ru ? "Входы" : "Inputs"}`,
        "",
        portsTable(runtime.inputs, locale),
        "",
        `## ${ru ? "Выходы" : "Outputs"}`,
        "",
        portsTable(runtime.outputs, locale)
      ].join("\n")
    : ru
      ? `# ${escapeMarkdown(title)}\n\nНода не найдена в текущем ответе \`/object_info\`.`
      : `# ${escapeMarkdown(title)}\n\nThis node is not present in the current \`/object_info\` response.`;

  return {
    manifest: {
      articleId: `generated:${classType}:${locale}`,
      kind: "core",
      locale,
      runtimeIdentity: {
        classType,
        aliases: [],
        kind: runtime?.kind ?? "server",
        packageId: runtime?.packageId,
        pythonModule: runtime?.pythonModule
      },
      searchAliases: [],
      status: runtime?.deprecated
        ? "deprecated"
        : runtime?.experimental
          ? "experimental"
          : "draft",
      compatibility: {},
      relations: { related: [], alternatives: [] },
      assets: [],
      editorial: { schemaHash: runtime?.schemaHash },
      sources: []
    },
    title,
    summary: ru
      ? "Автоматическая карточка из актуальной схемы ComfyUI. Редакторская статья ещё не подготовлена."
      : "Generated from the current ComfyUI schema. An editorial article is not available yet.",
    tags: [classType, runtime?.category ?? "uncategorized"],
    concepts: [],
    body
  };
}
