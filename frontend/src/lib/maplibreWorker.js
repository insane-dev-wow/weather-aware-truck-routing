import { setWorkerUrl } from "maplibre-gl";
// ?worker&url makes Vite emit a self-contained worker chunk (includes shared code).
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

setWorkerUrl(workerUrl);
