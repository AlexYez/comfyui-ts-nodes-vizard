declare module "*/scripts/app.js" {
  export const app: unknown;
}

declare module "*/scripts/api.js" {
  export const api: unknown;
}

declare module "*?raw" {
  const text: string;
  export default text;
}
