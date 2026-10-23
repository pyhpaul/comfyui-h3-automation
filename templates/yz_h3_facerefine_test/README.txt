TEST-ONLY FaceRefine post-pass (小脸修脸). Does not touch production yz_h3_ep_unit
or the 文武双全 generation template.

Goal
----
Take one already-rendered wenwu TEST mp4 (small/collapsed face), run
ComfyUI-H3-FaceRefine (detect → crop → H3 redraw → stitch), archive the
refined clip to a NEW Feiniu batch for A/B.

Source clips (already pulled from Feiniu while GPU is off)
---------------------------------------------------------
Batch: 文武双全TEST-黑手党EP01（10.19）
Local: jobs/facerefine_test/source_U01/EP01-U01-mafia2-wenwu_00001-audio.mp4
       jobs/facerefine_test/source_U02/  (same layout)
Remote: H3_comfyUI_5090/archive/文武双全TEST-黑手党EP01（10.19）/EP01/U0N/
Pick the unit whose face looks worse for the first FaceRefine run.

Local staging (already done, GPU off)
-------------------------------------
.cache/facerefine_prep/
  ComfyUI-H3-FaceRefine/          # custom nodes
  ComfyUI-H3-NativeAudioLock/     # lipsync lock used by example graphs
  models/ultralytics/bbox/face_yolov8m.pt
  models/ultralytics/segm/person_yolov8m-seg.pt

Boot checklist (when pod is back)
---------------------------------
1. Chenyu SSH host/port → remote_comfy_h3.sh restart → switch_gpu_tunnel.sh
2. curl http://192.168.50.106:8190/system_stats  (CUDA present)
3. python scripts/ops/install_facerefine_gpu.py --pip
4. bash scripts/ops/remote_comfy_h3.sh restart   # reload custom nodes
5. python scripts/ops/install_facerefine_gpu.py --check
   Expect: H3FaceTrackCrop OK, face_yolov8m present.
   If MISSING_IMPACT: install ComfyUI-Impact-Pack (registers ultralytics folders).
   If MISSING_VHS: install ComfyUI-VideoHelperSuite (save + Auto Select load).
6. Open workflow_ui.auto_select.source.json on Comfy UI, re-pick our H3
   unet/clip/vae (example names may differ), mute GGUF if unused, point
   VHS_LoadVideoPath at the uploaded source mp4, Save (API Format) →
   replace templates/yz_h3_facerefine_test/workflow_api.json
7. Ask for a new --feiniu-batch name, then:
     PYTHONPATH=src COMFY_BASE_URL=http://192.168.50.106:8190 \
       python scripts/run_facerefine_test.py \
         --video <local-or-downloaded-mp4> \
         --prompt-file <matching prompt_h3.txt> \
         --feiniu-batch '<新批次>' \
         --episode EP01 --unit U01

Notes
-----
- This is a post-pass on finished video, not SelfLift 二采.
- highres_tiling stays irrelevant here; FaceRefine uses its own 768 crop canvas.
- Do not reuse the previous Feiniu batch name.
- Production graphs stay untouched.
