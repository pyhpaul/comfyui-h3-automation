# H3 Gate 0 U02 offline quality screen (2026-09-27)

Status: **fresh-agent static-frame blind review complete; operator reports
the two clips are basically consistent**. The
5090 rental is back to production. This step used only local D: media and did
not access or submit another rental/Colab task.

## Material and objective checks

The two 12.75 s U02 source MP4s were copied under neutral filenames to
`/mnt/d/comfyui-h3-backups/rental-20260924-5090/a100-perf-pilot/gate0-5090-20260927-01/quality-review/`.
Their original hashes were checked against the frozen A100 C1 validation and
the new 5090 source-side evaluation before copying. The neutral copies are
for viewing; the originals and validation receipts remain separate.

Both clips have 306 H.264 frames at 768x1376/24 fps and AAC 32 kHz stereo.
Frame-aligned FFmpeg SSIM across all 306 frames is 0.840001 overall. The
largest pixel-level difference is near 11-12.75 s. SSIM measures similarity,
not which image is better. FFmpeg `apsnr` on decoded audio reports approximately
173.1 dB for both channels; decoded PCM SHA-256 values differ, so do not call
the sound byte-identical. Neither metric verifies dialogue intelligibility,
sound quality, or lip sync.

## Agent frame review boundary

An existing review agent viewed each neutral clip at about 58 sampled times,
with denser 8 fps sampling near the ending. It did not play either video
continuously and could not listen to audio. It recognized one clip from a
previous A/B review, so this is **not an independent blind review**. Its
low-confidence, prior-exposure-contaminated preference must not be used to
select a GPU/profile.

The agent found the same intelligible shot sequence and broadly stable
characters in both. It noted hand/whip contact and pronounced yellow teeth
around 8-10 s in both; one ending has more background guards, while the other
has a simpler background. It did not identify a decisive visual defect or
clear quality winner from sampled frames. This does not rule out short flicker,
continuous-motion defects, audio defects, or lip-sync errors.

## Fresh independent blind review

A new agent with no inherited task history was given only the two neutral MP4
paths and was instructed not to inspect manifests, source paths, hashes, or
the hardware mapping. It sampled every 0.25 s: **51 of 306 frames per clip**,
covering 0.00-12.50 s. It judged **no meaningful visual quality difference**
and found no definite fatal defect in those frames. In both clips the eye-patch
character and clothing remain broadly stable; hand/whip geometry has mild
generated artifacts and the teeth look unnaturally even/yellow. The ending
young man and scene are stable in the sampled frames. Confidence is medium-
high for the sampled frames, only medium for the full clip.

The fresh agent could not play the video continuously. Its attempt to pass
audio as input returned `audio content omitted because you do not support
audio input`; it **did not hear either clip**. Accordingly this is an
independent static-frame blind review, not full audiovisual acceptance. The
earlier recognition-contaminated review above remains documented but is not
used for the A/B decision. The hardware mapping was withheld until operator
feedback.

## Operator feedback and unblinding

After viewing the neutral pair, the operator reported that the results are
basically consistent. The pair is now unblinded: `clip_a.mp4` is the new RTX
5090 run; `clip_b.mp4` is the archived A100 C1 run. This is an operator
assessment of this one pair, not a demonstrated per-run quality guarantee.
No separate scored audio, lip-sync, or repeated-seed variance review was
recorded.

For this same-input one-pass U02, history-derived server wall was 625.406 s
on the RTX 5090 and 1324.348 s on A100 C1. The RTX 5090 took 698.942 s less
time (52.8% shorter; 2.118x throughput for the generation interval). This
excludes Colab startup, model restore, transfer, backup, rental billing and
queue delays. It is a deployment-combination comparison, not a pure GPU
silicon benchmark or a multi-run stability estimate.

## Next gate

If an audio/lip-sync acceptance claim is required, an operator should still
listen end to end and record timestamped defects. The review prompt is in
`quality-review/README.md`. No additional GPU run is required for that gate.

The existing 5090 result is a single deployment-combination timing screen,
not a variance estimate, cost-per-video result, production migration decision,
or proof of equal visual/audio quality. If quality passes, the next proposal
should separately assess 5090/Blackwell deployment and economics; if A100 is
mandatory, a mechanism-specific A100 optimization experiment needs its own
budget and quality-preserving acceptance criteria.

As diagnostic context only, the isolated C1 and 5090 server logs display
approximately 20:08 and 08:51 inside their respective 12-step tqdm bars.
Their difference accounts for most of the 698.942 s server-wall gap; this
points toward sampling rather than final encoding as the next A100 profiling
target. The logs do not provide the same prompt-bound sampler clock on both
machines, so these tqdm values must not be promoted to an accepted sampler
speed ratio.
