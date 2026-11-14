// Login hero media. Files live in public/media/ (raw sources in media-src/, gitignored).
// Set a path when the file exists; leave null otherwise. The hero picks, in order:
//   1. video  - only on wide screens without reduced motion, after it can play smoothly
//   2. image  - the poster, with a slow 18 s drift (transform only, paused for reduced motion)
//   3. the CSS "night corridor" fallback (no files needed)
export const loginMedia: { video: string | null; poster: string | null } = {
  video: null, // e.g. '/media/login-corridor.mp4'  (H.264, no audio, < ~6 MB)
  poster: null, // e.g. '/media/login-corridor.jpg'
}
