import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const objectInfo = JSON.parse(fs.readFileSync(path.join(root, "content/runtime/comfyui-0.32.0.object-info.json"), "utf8"));
const articleIds = process.argv.slice(2);

if (!articleIds.length) throw new Error("Pass article IDs to backfill");

const scalarTypes = new Set(["INT", "FLOAT", "BOOLEAN", "STRING"]);

function widgetValue(spec) {
  const [type, options = {}] = spec;
  if (Array.isArray(type)) return type[0];
  if (Object.hasOwn(options, "default")) return options.default;
  if (type === "INT" || type === "FLOAT") return options.min ?? 0;
  if (type === "BOOLEAN") return false;
  if (type === "STRING") return "";
  return undefined;
}

function isWidget(spec) {
  return Array.isArray(spec[0]) || scalarTypes.has(spec[0]);
}

function slugify(value) {
  return value
    .replace(/^core\./, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
}

for (const articleId of articleIds) {
  const articleDir = path.join(root, "content/articles/core", articleId.replace(/^core\./, ""));
  const manifestPath = path.join(articleDir, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const classType = manifest.runtimeIdentity.classType;
  const definition = objectInfo[classType];
  if (!definition) throw new Error(`Missing runtime definition: ${classType}`);

  const slug = `${slugify(articleId)}-local-check`;
  const recipeId = `recipe.${slug}`;
  const fragmentId = `fragment.${slug}`;
  const recipeDir = path.join(root, "content/recipes", slug);
  fs.mkdirSync(recipeDir, { recursive: true });

  const externalInputs = [];
  const settings = {};
  for (const [name, spec] of Object.entries(definition.input?.required ?? {})) {
    if (isWidget(spec)) settings[name] = widgetValue(spec);
    else externalInputs.push({ id: name.replace(/[^a-zA-Z0-9_-]/g, "-"), type: spec[0], to: "target", input: name });
  }

  const source = manifest.sources?.[0];
  const title = `${manifest.title}: локальная проверочная заготовка`;
  const fragment = {
    $schema: "../../schemas/recipe-fragment.schema.v1.json",
    schemaVersion: "1.0",
    fragmentId,
    title,
    externalInputs,
    nodes: [{ ref: "target", classType, role: "Проверить входы ноды в локальном графе", settings }],
    connections: [],
  };
  const recipe = {
    $schema: "../../schemas/recipe.schema.v1.json",
    schemaVersion: "1.0",
    recipeId,
    locale: "ru",
    title,
    summary: "Добавляет одну ноду с точными обязательными портами и безопасными значениями виджетов из закреплённой схемы runtime.",
    body: "ru.md",
    difficulty: "advanced",
    articleIds: [articleId],
    requirements: ["ComfyUI 0.32.0 или совместимая версия", "Локальные модели и входные данные, необходимые этой ноде"],
    fragment: { id: fragmentId, path: "fragment.json", format: "nodes-wizard-fragment/1.0" },
    editorial: {
      state: "draft",
      reviewedBy: "Автоматизированная сверка схемы runtime; исполнение полного графа и человеческое утверждение ожидаются",
      reviewedAt: "2026-08-20",
    },
    sources: [{
      title: source?.title ?? "ComfyUI v0.32.0 pinned source",
      url: source?.url ?? "https://github.com/Comfy-Org/ComfyUI/tree/c2bcbecd82ec5ae66594340b395c24ef0217b238",
      publisher: source?.publisher ?? "Comfy-Org",
      accessedAt: "2026-08-20",
    }],
  };
  const body = `# ${title}\n\nЭтот фрагмент добавляет только \`${classType}\`. Обязательные соединяемые входы вынесены наружу, а значения виджетов взяты из закреплённого снимка \`/object_info\` ComfyUI 0.32.0.\n\nЭто диагностическая заготовка для локального графа, а не готовый workflow. После вставки подключите совместимые модели и данные, проверьте размеры и типы, затем выполните граф вручную. Полное исполнение с весами ещё не подтверждено человеком.\n`;

  fs.writeFileSync(path.join(recipeDir, "fragment.json"), `${JSON.stringify(fragment)}\n`);
  fs.writeFileSync(path.join(recipeDir, "recipe.json"), `${JSON.stringify(recipe)}\n`);
  fs.writeFileSync(path.join(recipeDir, "ru.md"), body);

  manifest.assets = [
    ...(manifest.assets ?? []).filter((asset) => asset.id !== recipeId),
    { type: "recipe", id: recipeId, label: "Проверочная заготовка локального графа" },
  ];
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest)}\n`);
}
