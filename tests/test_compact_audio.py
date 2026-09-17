"""Objective checks for the values and channels shown in the approved UI."""
from array import array
import json
import math
import shutil
import subprocess
import wave

import pytest

from backend.app_paths import AppPaths
from backend.audio_processing.equalizer import effect_biquads, response_db
from backend.audio_processing.ffmpeg_tools import AudioEffects, MixStem, _build_mix_filter, _effect_filters, stereo_waveform_peaks
from backend.compact_model import MAX_STEM_PERCENT, position_to_volume, volume_to_position
from backend.project_store import validate_edits, read_project, FORMAT


def test_fader_unity_headroom_silence_and_project_validation():
    assert volume_to_position(100) == pytest.approx(.67)
    assert position_to_volume(.67) == pytest.approx(100)
    assert position_to_volume(1) == pytest.approx(MAX_STEM_PERCENT)
    assert 20*math.log10(position_to_volume(1)/100) == pytest.approx(12)
    assert position_to_volume(0) == 0
    for db in (-48, -24, -12, 0, 6, 12):
        gain = 100 * 10 ** (db / 20)
        assert position_to_volume(volume_to_position(gain)) == pytest.approx(gain)
    state = validate_edits({"stems": {"vocals": {"volume": MAX_STEM_PERCENT}}})
    assert state["stems"]["vocals"]["volume"] == MAX_STEM_PERCENT
    with pytest.raises(ValueError):
        validate_edits({"stems": {"vocals": {"volume": MAX_STEM_PERCENT+1}}})


def test_legacy_project_keeps_two_pole_cut_filter(tmp_path):
    path = tmp_path / "legacy.kwaksplit"
    path.write_text(json.dumps({"format": FORMAT, "version": 1, "source": "old.wav", "edits": {
        "high_pass": 120, "eq_low_shape": "Bell", "loop": False}}), encoding="utf-8")
    old = read_project(path)
    assert old["edits"]["high_pass_slope"] == 12
    assert old["edits"]["eq_low_shape"] == "Bell"
    assert old["edits"]["loop"] is False


def test_stereo_peaks_do_not_cancel_or_copy_channels(tmp_path):
    source = tmp_path / "opposite.wav"
    data = array("h")
    for i in range(4800):
        sample = int(24000*math.sin(2*math.pi*1000*i/48000))
        data.extend((sample, -sample//2))
    with wave.open(str(source), "wb") as f:
        f.setparams((2, 2, 48000, 0, "NONE", ""))
        f.writeframes(data.tobytes())
    peaks = stereo_waveform_peaks(AppPaths(tmp_path), source, 50)
    assert max(p[0] for p in peaks) > .7
    assert max(p[1] for p in peaks) == pytest.approx(max(p[0] for p in peaks)/2, abs=.001)


@pytest.mark.parametrize("slope", (12, 24, 36, 48))
@pytest.mark.parametrize("kind,freq,probe", (("high_pass", 120, 120), ("high_pass", 120, 30),
                                             ("low_pass", 8000, 16000)))
def test_display_response_matches_rendered_audio(slope, kind, freq, probe):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required")
    effects = AudioEffects(**{kind+"_hz": freq, kind+"_slope": slope, kind+"_q": math.sqrt(.5)},
                           sample_rate=48000, limiter_enabled=False)
    result = subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                             f"aevalsrc=.125*sin(2*PI*{probe}*t):s=48000:d=2", "-af",
                             ",".join(_effect_filters(effects)), "-f", "f64le", "-"], capture_output=True,
                            check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    samples = array("d"); samples.frombytes(result.stdout)
    rms = math.sqrt(sum(x*x for x in samples[-24000:])/24000)
    measured = 20*math.log10(rms/(.125/math.sqrt(2)))
    displayed = response_db(effect_biquads(effects), probe, 48000)
    assert measured == pytest.approx(displayed, abs=.07)
    if probe == freq:
        assert measured == pytest.approx(-3.01, abs=.07)


@pytest.mark.parametrize("shape,frequency,gain,q,probe",(
    ("Low Shelf",180,9,.8,80),("High Shelf",6000,-9,.8,10000),
    ("Bell",1400,7,2.5,1200),("High Pass",120,0,1.2,120)))
def test_resonance_and_shelf_bell_curves_match_audio(shape,frequency,gain,q,probe):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:pytest.skip("FFmpeg required")
    if shape=="High Pass":
        effects=AudioEffects(high_pass_hz=frequency,high_pass_slope=48,high_pass_q=q,sample_rate=48000)
    else:
        effects=AudioEffects(mid_shape=shape,mid_freq=frequency,mid_db=gain,mid_q=q,sample_rate=48000)
    result=subprocess.run([ffmpeg,"-v","error","-f","lavfi","-i",
        f"aevalsrc=.01*sin(2*PI*{probe}*t):s=48000:d=2","-af",",".join(_effect_filters(effects)),
        "-f","f64le","-"],capture_output=True,check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    samples=array("d");samples.frombytes(result.stdout)
    rms=math.sqrt(sum(x*x for x in samples[-24000:])/24000)
    measured=20*math.log10(rms/(.01/math.sqrt(2)))
    assert measured==pytest.approx(response_db(effect_biquads(effects),probe,48000),abs=.07)


@pytest.mark.parametrize("amplitude",(.05,.5))
def test_limiter_preserves_quiet_gain_and_honors_ceiling(tmp_path,amplitude):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:pytest.skip("FFmpeg required")
    source=tmp_path/"limiter.wav"
    kwargs=dict(capture_output=True,check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    subprocess.run([ffmpeg,"-v","error","-f","lavfi","-i",
        f"aevalsrc={amplitude}*sin(2*PI*1000*t):s=48000:d=1","-c:a","pcm_f32le",str(source)],**kwargs)
    inputs,filters=_build_mix_filter([MixStem("source",source,1)],0,1,0,0,
        AudioEffects(sample_rate=48000,limiter_enabled=True,limiter_ceiling=.2))
    result=subprocess.run([ffmpeg,"-v","error",*inputs,"-filter_complex",filters,"-map","[outa]","-f","f64le","-"],**kwargs)
    samples=array("d");samples.frombytes(result.stdout)
    assert len(samples)==48000
    assert max(abs(x) for x in samples[2400:])==pytest.approx(min(amplitude,.2),abs=.0005)
