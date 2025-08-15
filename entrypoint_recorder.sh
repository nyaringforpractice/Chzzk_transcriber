#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Asia/Seoul}"
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

mkdir -p /data/chunks/a /data/chunks/b

echo "[recorder] TZ=${TZ}, CHUNK_SECONDS=${CHUNK_SECONDS}, OVERLAP_ENABLE=${OVERLAP_ENABLE:-false}, OVERLAP_MS=${OVERLAP_MS:-0}"

while true; do
  echo "[recorder] connecting streamlink..."
  if [[ "${OVERLAP_ENABLE:-false}" == "true" ]]; then
    # 두갈래 (A: 즉시, B: 지연)
    streamlink "https://chzzk.naver.com/live/${CHANNEL_ID}" best \
      --http-cookie "NID_AUT=${NID_AUT}" \
      --http-cookie "NID_SES=${NID_SES}" -O \
    | ffmpeg -hide_banner -loglevel warning -nostdin -i pipe:0 \
        -filter_complex "aformat=channel_layouts=mono,aresample=16000,asplit=2[a][b];[b]adelay=${OVERLAP_MS}[bd]" \
        -map "[a]"  -f segment -strftime 1 -segment_time ${CHUNK_SECONDS} -reset_timestamps 1 -c:a pcm_s16le "/data/chunks/a/%Y%m%d-%H%M%S.wav" \
        -map "[bd]" -f segment -strftime 1 -segment_time ${CHUNK_SECONDS} -reset_timestamps 1 -c:a pcm_s16le "/data/chunks/b/%Y%m%d-%H%M%S.wav" \
    || true
  else
    # 한갈래 (경량)
    streamlink "https://chzzk.naver.com/live/${CHANNEL_ID}" best \
      --http-cookie "NID_AUT=${NID_AUT}" \
      --http-cookie "NID_SES=${NID_SES}" -O \
    | ffmpeg -hide_banner -loglevel warning -nostdin -i pipe:0 \
        -af "aformat=channel_layouts=mono,aresample=16000" \
        -f segment -strftime 1 -segment_time ${CHUNK_SECONDS} -reset_timestamps 1 -c:a pcm_s16le "/data/chunks/a/%Y%m%d-%H%M%S.wav" \
    || true
  fi

  echo "[recorder] stream ended. retry in 3s"
  sleep 3
done
