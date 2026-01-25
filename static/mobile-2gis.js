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
      return `https://2gis.kz/almaty/geo/${lon},${lat}`;
    }
    if (hint) {
      return `https://2gis.kz/almaty/search/${encodeURIComponent(hint)}`;
    }
    return null;
  }

  global.parse2gisCoord = parseCoord;
  global.build2gisWebUrl = build2gisWebUrl;
})(typeof window !== "undefined" ? window : globalThis);
