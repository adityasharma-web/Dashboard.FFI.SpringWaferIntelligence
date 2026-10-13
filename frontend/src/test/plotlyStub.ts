/* Test stand-in for plotly.js-dist-min (aliased in vite.config.ts): jsdom has
   no WebGL/canvas, and the tests assert on the figure JSON handed to Plotly
   rather than on rendered pixels. */

export interface ReactCall {
  data: Record<string, unknown>[]
  layout: Record<string, unknown>
}

export const reactCalls: ReactCall[] = []

const Plotly = {
  react(
    node: HTMLElement,
    data: Record<string, unknown>[],
    layout: Record<string, unknown>,
  ): Promise<void> {
    void node
    reactCalls.push({ data, layout })
    return Promise.resolve()
  },
  purge(node: HTMLElement): void {
    void node
  },
}

export default Plotly
