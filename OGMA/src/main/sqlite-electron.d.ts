declare module 'sqlite-electron' {
  export function setdbPath(path: string, isUri?: boolean, autocommit?: boolean): Promise<boolean>
  export function executeQuery(query: string, values?: any[] | Record<string, any>): Promise<any[]>
  export function executeScript(script: string): Promise<boolean>
  export function executeMany(query: string, values: any[][]): Promise<boolean>
  export function closeDb(): Promise<boolean>
}
