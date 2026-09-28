// echarts theme matching the sheet: cream 1px lines, dashed hairline grid,
// monospace tick labels, panel-style tooltips, no gradients.
import * as echarts from "echarts";

export const CREAM = "#e8e4d8";
export const MUTED = "#8a8780";
export const LINE = "rgba(232,228,216,0.22)";
export const ACCENT = "#e8623c";
export const MONO = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace';

const axis = {
  axisLine: { lineStyle: { color: LINE } },
  axisTick: { lineStyle: { color: LINE } },
  axisLabel: { color: MUTED, fontFamily: MONO, fontSize: 10 },
  splitLine: { lineStyle: { color: "rgba(232,228,216,0.10)", type: "dashed" } },
  nameTextStyle: { color: MUTED, fontFamily: MONO, fontSize: 10 },
};

echarts.registerTheme("lab", {
  backgroundColor: "transparent",
  color: [CREAM, ACCENT, MUTED],
  textStyle: { fontFamily: MONO, color: CREAM },
  title: { textStyle: { color: CREAM, fontFamily: MONO, fontSize: 12, fontWeight: 400 } },
  line: { lineStyle: { width: 1 }, symbolSize: 3, smooth: false },
  categoryAxis: axis,
  valueAxis: axis,
  logAxis: axis,
  timeAxis: axis,
  tooltip: {
    backgroundColor: "#070707",
    borderColor: LINE,
    borderWidth: 1,
    textStyle: { color: CREAM, fontFamily: MONO, fontSize: 11 },
    extraCssText: "border-radius:0;padding:6px 8px;",
  },
});
