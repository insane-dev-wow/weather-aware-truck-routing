import { createTheme } from "@mui/material/styles";

const FONT_STACK =
  '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif';

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#245ba8", dark: "#17457f", light: "#7fa2d2" },
    secondary: { main: "#64748b" },
    success: { main: "#278362" },
    warning: { main: "#b7791f" },
    error: { main: "#b83a3a" },
    background: { default: "#f3f4f6", paper: "#ffffff" },
    text: { primary: "#202b3c", secondary: "#606d7e" },
    divider: "#dfe3e8",
  },
  shape: { borderRadius: 6 },
  typography: {
    fontFamily: FONT_STACK,
    h6: { fontSize: "1rem", fontWeight: 650 },
    subtitle1: { fontSize: ".95rem", fontWeight: 650 },
    subtitle2: { fontSize: ".85rem", fontWeight: 650 },
    body1: { fontSize: ".875rem" },
    body2: { fontSize: ".8125rem" },
    caption: { fontSize: ".73rem" },
    button: { textTransform: "none", fontWeight: 600 },
    overline: { textTransform: "none" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: { body: { WebkitFontSmoothing: "antialiased" } },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { backgroundImage: "none" } },
    },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 8 } } },
  },
});
