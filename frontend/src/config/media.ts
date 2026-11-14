// Login hero media. Files live in public/media/ (raw sources in media-src/, gitignored).
// Set a path when the file exists; leave null otherwise. The hero picks, in order:
//   1. video  - only on wide screens without reduced motion, after it can play smoothly
//   2. image  - the poster, with a slow 18 s drift (transform only, paused for reduced motion)
//   3. the CSS "night corridor" fallback (no files needed)
//
// Current clip: sunset railway yard, 13.5 s, 736x414, supplied by the project owner
// (frontend/media-src/login-train-window.mp4). Web copy: audio removed, 0.6 s fade to dark at
// both ends so the loop has no jump, H.264 CRF 22, 1.06 MB. Poster: frame at 1.0 s.
export const loginMedia: { video: string | null; poster: string | null } = {
  video: '/media/login-railway-sunset.mp4',
  poster: '/media/login-railway-sunset.jpg',
}
