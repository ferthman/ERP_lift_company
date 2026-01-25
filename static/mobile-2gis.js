(function (global) {
  function parseCoord(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === "string" && value.trim() === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function build2gisWebUrl(ticket) {
    if (!ticket) return null;
    const lon = parseCoord(ticket.lng ?? ticket.lon);
    const lat = parseCoord(ticket.lat);
    const hasCoords =
      lat !== null &&
      lon !== null &&
      lat >= -90 &&
      lat <= 90 &&
      lon >= -180 &&
      lon <= 180;
    const address = (ticket.address || "").trim();
    const objectName = (ticket.object_name || "").trim();
    const hint = [objectName, address].filter(Boolean).join(", ");
    // Guardrail checks:
    // - null/empty coords -> use address search
    // - "0"/0 coords remain valid (0,0) unless business rules change
    if (hasCoords) {
      return `https://2gis.kz/routeSearch/rsType/car/to/${lon},${lat}`;
    }
    if (hint) {
      return `https://2gis.kz/search/${encodeURIComponent(hint)}`;
    }
    return null;
  }

  function build2gisAppUrl(ticket) {
    if (!ticket) return null;
    const lon = parseCoord(ticket.lng ?? ticket.lon);
    const lat = parseCoord(ticket.lat);
    const hasCoords =
      lat !== null &&
      lon !== null &&
      lat >= -90 &&
      lat <= 90 &&
      lon >= -180 &&
      lon <= 180;
    if (!hasCoords) return null;
    return `dgis://2gis.ru/routeSearch/rsType/car/to/${lon},${lat}`;
  }

  global.parse2gisCoord = parseCoord;
  global.build2gisAppUrl = build2gisAppUrl;
  global.build2gisWebUrl = build2gisWebUrl;
})(typeof window !== "undefined" ? window : globalThis);
