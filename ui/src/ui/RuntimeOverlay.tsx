import type { LocaleCode, RuntimeNodeDefinition } from "../types/contracts";
import { runtimeOverlayData, type RuntimeOverlayPort } from "./runtimeOverlayData";

function Ports({
  ports,
  locale
}: {
  ports: RuntimeOverlayPort[];
  locale: LocaleCode;
}) {
  const ru = locale === "ru";
  if (ports.length === 0) {
    return <p className="nw-runtime-empty">{ru ? "Порты не объявлены." : "No declared ports."}</p>;
  }
  return (
    <div className="nw-runtime-table-wrap">
      <table className="nw-runtime-table">
        <thead>
          <tr>
            <th>{ru ? "Имя" : "Name"}</th>
            <th>{ru ? "Тип" : "Type"}</th>
            <th>{ru ? "Режим" : "Mode"}</th>
            <th>{ru ? "Ограничения" : "Constraints"}</th>
          </tr>
        </thead>
        <tbody>
          {ports.map((port) => (
            <tr key={`${port.mode}:${port.name}`}>
              <td title={port.tooltip}>{port.name}</td>
              <td><code>{port.type}{port.list ? "[]" : ""}</code></td>
              <td>
                {port.mode === "required"
                  ? ru ? "обязательный" : "required"
                  : port.mode === "optional"
                    ? ru ? "необязательный" : "optional"
                    : ru ? "выход" : "output"}
              </td>
              <td>
                {port.constraints.length > 0
                  ? port.constraints.map(({ key, value }) => (
                      <span className="nw-constraint" key={key}><b>{key}</b>: {value}</span>
                    ))
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RuntimeOverlay({
  runtime,
  locale
}: {
  runtime: RuntimeNodeDefinition;
  locale: LocaleCode;
}) {
  const data = runtimeOverlayData(runtime);
  const ru = locale === "ru";
  return (
    <section className="nw-runtime" data-testid="runtime-overlay" aria-labelledby="nw-runtime-title">
      <div className="nw-runtime-heading">
        <div>
          <div className="nw-kicker">{ru ? "Живая схема ComfyUI" : "Live ComfyUI schema"}</div>
          <h2 id="nw-runtime-title">{ru ? "Установленная нода" : "Installed node"}</h2>
        </div>
        <span className="nw-badge" data-tone="success">/object_info</span>
      </div>
      <dl className="nw-runtime-meta">
        <div><dt>class_type</dt><dd><code>{data.classType}</code></dd></div>
        <div><dt>{ru ? "Категория" : "Category"}</dt><dd>{data.category}</dd></div>
        {data.packageId ? <div><dt>package</dt><dd><code>{data.packageId}</code></dd></div> : null}
        {data.pythonModule ? <div><dt>module</dt><dd><code>{data.pythonModule}</code></dd></div> : null}
      </dl>
      {data.deprecated || data.experimental || data.apiNode ? (
        <div className="nw-badges">
          {data.deprecated ? <span className="nw-badge" data-tone="warn">deprecated</span> : null}
          {data.experimental ? <span className="nw-badge" data-tone="warn">experimental</span> : null}
          {data.apiNode ? <span className="nw-badge">API node</span> : null}
        </div>
      ) : null}
      <h3>{ru ? "Входы" : "Inputs"}</h3>
      <Ports ports={data.inputs} locale={locale} />
      <h3>{ru ? "Выходы" : "Outputs"}</h3>
      <Ports ports={data.outputs} locale={locale} />
      <details className="nw-runtime-hash">
        <summary>{ru ? "Fingerprint схемы" : "Schema fingerprint"}</summary>
        <code>{data.schemaHash}</code>
      </details>
    </section>
  );
}
