from fractions import Fraction

import av
import numpy as np
import pytest

from app.streaming.decoder import DecodeError, H264Decoder
from app.streaming.protocol import VideoPacket


def encoded_frame(width=64, height=96, color=(200, 30, 70)):
    encoder = av.CodecContext.create("libx264", "w")
    encoder.width, encoder.height = width, height
    encoder.pix_fmt = "yuv420p"
    encoder.time_base = Fraction(1, 30)
    encoder.options = {"preset": "ultrafast", "tune": "zerolatency", "crf": "18"}
    rgb = np.full((height, width, 3), color, dtype=np.uint8)
    frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
    return b"".join(bytes(packet) for packet in encoder.encode(frame) + encoder.encode(None))


def test_actual_h264_encode_decode_rgb_and_resolution_change():
    decoder = H264Decoder()
    first = decoder.decode(VideoPacket(encoded_frame(), 0, False, True))
    assert len(first) == 1
    assert (first[0].width, first[0].height) == (64, 96)
    assert isinstance(first[0].rgb, bytes)
    rgb = np.frombuffer(first[0].rgb, dtype=np.uint8).reshape(96, 64, 3)
    assert np.abs(rgb.mean(axis=(0, 1)) - (200, 30, 70)).max() < 6
    second = decoder.decode(VideoPacket(encoded_frame(96, 64), 1000, False, True))
    assert len(second) == 1 and (second[0].width, second[0].height) == (96, 64)
    decoder.close()
    with pytest.raises(DecodeError, match="closed"):
        decoder.decode(VideoPacket(b"bad", 1, False, False))


def test_config_is_joined_to_following_media_before_decode():
    # The first SPS/PPS NAL units in Annex-B can be delivered independently by
    # Android MediaCodec. Split before the SEI start code of this actual encoder.
    data = encoded_frame()
    index = data.find(b"\x00\x00\x01\x06")
    assert index > 0
    decoder = H264Decoder()
    assert decoder.decode(VideoPacket(data[:index], None, True, False)) == []
    frames = decoder.decode(VideoPacket(data[index:], 0, False, True))
    assert len(frames) == 1 and frames[0].width == 64


def test_config_is_bounded_and_decode_errors_are_explicit():
    decoder = H264Decoder(max_config_bytes=4)
    with pytest.raises(DecodeError, match="configuration"):
        decoder.decode(VideoPacket(b"12345", None, True, False))
    with pytest.raises(DecodeError, match="rejected"):
        decoder.decode(VideoPacket(b"not h264", 0, False, False))


def test_decoded_dimensions_are_bounded():
    with pytest.raises(DecodeError, match="dimensions"):
        H264Decoder(max_pixels=50).decode(VideoPacket(encoded_frame(), 0, False, True))
