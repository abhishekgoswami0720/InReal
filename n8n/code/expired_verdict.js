// "Link dead or closed" verdict (n8n Code node, runs once for each listing)
// The apply page returned 404/410 or says applications are closed. Not a scam judgement:
// the card is greyed out on the dashboard as expired, and nothing is sent to the AI stages.

function expiredVerdict(listing, link) {
  const why = link.link_state === "closed"
    ? `Apply page says "${link.closed_phrase}"`
    : `Apply page returned HTTP ${link.http_status} (${link.link_state})`;
  return { id: listing.id, status: "expired", scam_risk: 0, reasons: [why], decided_by: "link_check" };
}

// ==== n8n glue (below this line runs only inside n8n) ====
return { json: { verdict: expiredVerdict($('Fetch pending listings').item.json, $json) } };
