# Supabase (database + Google login)

Project: **InReal** (region ap-south-1, Mumbai), created 19 Oct 2026.

`schema.sql` is the database as it stands: users (`profiles`), the shared list (`listings`),
`bookmarks`, and the row-level-security rules that do the locking. It was applied as three
migrations (`inreal_core`, `private_helpers_no_drop`, `listing_timestamps`); this file is the same end state in one place.

Who sees what (checked with test users, 19 Oct):

| | listings table | teaser_listings() / listing_stats() |
|---|---|---|
| not signed in | nothing | 6 newest verified posts (no text, no apply link) and the real counts |
| signed in | every verified and "needs a look" post, at once (no plans for now; the page shows the user's field, verified only by default) | same |

Blocked posts are visible to no one through the API. Users can't change their own `plan` or `is_admin`.
The laptop pipeline writes `listings` with the secret key from `.env` (it bypasses RLS); that key never goes to a browser.
