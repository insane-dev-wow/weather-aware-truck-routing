import AltRouteRounded from "@mui/icons-material/AltRouteRounded";
import HelpOutlineRounded from "@mui/icons-material/HelpOutlineRounded";
export default function AppHeader({ onOpenGuide }) {
  return (
    <header className="app-header">
      <div className="header-inner">
        <a href="#" className="brand" aria-label="Wayline home">
          <span className="brand-mark">
            <AltRouteRounded />
          </span>
          <span>Wayline</span>
        </a>
        <div className="header-divider" />
        <span className="header-product">Fleet routing</span>
        <nav className="header-nav" aria-label="Main navigation">
          <a className="nav-active" href="#trip-planner">
            Planning
          </a>
          <button type="button" onClick={onOpenGuide}>
            <HelpOutlineRounded /> Routing rules
          </button>
        </nav>
      </div>
    </header>
  );
}
