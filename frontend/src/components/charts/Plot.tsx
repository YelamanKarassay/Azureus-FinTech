import createPlotlyComponentModule from 'react-plotly.js/factory.js'
import Plotly from 'plotly.js-basic-dist-min'

const createPlotlyComponent =
  typeof createPlotlyComponentModule === 'function'
    ? createPlotlyComponentModule
    : createPlotlyComponentModule.default

export const Plot = createPlotlyComponent(Plotly)
