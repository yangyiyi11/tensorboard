# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Audio summaries and TensorFlow operations to create them.

An audio summary stores a rank-2 string tensor of shape `[k, 2]`, where
`k` is the number of audio clips recorded in the summary. Each row of
the tensor is a pair `[encoded_audio, label]`, where `encoded_audio` is
a binary string whose encoding is specified in the summary metadata, and
`label` is a UTF-8 encoded Markdown string describing the audio clip.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import functools

import numpy as np
import tensorflow as tf

from tensorboard import util
from tensorboard.plugins.audio import metadata


def op(name,
       audio,
       sample_rate,
       labels=None,
       max_outputs=3,
       encoding=None,
       display_name=None,
       description=None,
       collections=None):
  """Create an audio summary op for use in a TensorFlow graph.

  Arguments:
    name: A unique name for the generated summary node.
    audio: A `Tensor` representing audio data with shape `[k, t, c]`,
      where `k` is the number of audio clips, `t` is the number of
      frames, and `c` is the number of channels. Elements should be
      floating-point values in `[-1.0, 1.0]`. Any of the dimensions may
      be statically unknown (i.e., `None`).
    sample_rate: An `int` or rank-0 `int32` `Tensor` that represents the
      sample rate, in Hz. Must be positive.
    labels: Optional `string` `Tensor`, a vector whose length is the
      first dimension of `audio`, where `labels[i]` contains arbitrary
      textual information about `audio[i]`. (For instance, this could be
      some text that a TTS system was supposed to produce.) Markdown is
      supported. Contents should be UTF-8.
    max_outputs: Optional `int` or rank-0 integer `Tensor`. At most this
      many audio clips will be emitted at each step. When more than
      `max_outputs` many clips are provided, the first `max_outputs`
      many clips will be used and the rest silently discarded.
    encoding: A constant `str` (not string tensor) indicating the
      desired encoding. You can choose any format you like, as long as
      it's "wav". Please see the "API compatibility note" below.
    display_name: Optional name for this summary in TensorBoard, as a
      constant `str`. Defaults to `name`.
    description: Optional long-form description for this summary, as a
      constant `str`. Markdown is supported. Defaults to empty.
    collections: Optional list of graph collections keys. The new
      summary op is added to these collections. Defaults to
      `[Graph Keys.SUMMARIES]`.

  Returns:
    A TensorFlow summary op.

  API compatibility note: The default value of the `encoding`
  argument is _not_ guaranteed to remain unchanged across TensorBoard
  versions. In the future, we will by default encode as FLAC instead of
  as WAV. If the specific format is important to you, please provide a
  file format explicitly.
  """

  if display_name is None:
    display_name = name
  if encoding is None:
    encoding = 'wav'

  if encoding == 'wav':
    encoding = metadata.Encoding.Value('WAV')
    encoder = functools.partial(tf.contrib.ffmpeg.encode_audio,
                                samples_per_second=sample_rate,
                                file_format='wav')
  else:
    raise ValueError('Unknown encoding: %r' % encoding)

  with tf.name_scope(name), \
       tf.control_dependencies([tf.assert_rank(audio, 3)]):
    limited_audio = audio[:max_outputs]
    encoded_audio = tf.map_fn(encoder, limited_audio,
                              dtype=tf.string,
                              name='encode_each_audio')
    if labels is None:
      limited_labels = tf.tile([''], tf.shape(limited_audio)[:1])
    else:
      limited_labels = labels[:max_outputs]
    tensor = tf.transpose(tf.stack([encoded_audio, limited_labels]))
    summary_metadata = metadata.create_summary_metadata(
        display_name=display_name,
        description=description,
        encoding=encoding)
    return tf.summary.tensor_summary(name='audio_summary',
                                     tensor=tensor,
                                     collections=collections,
                                     summary_metadata=summary_metadata)


def pb(name,
       audio,
       sample_rate,
       labels=None,
       max_outputs=3,
       encoding=None,
       display_name=None,
       description=None):
  """Create an audio summary protobuf.

  This behaves as if you were to create an `op` with the same arguments
  (wrapped with constant tensors where appropriate) and then execute
  that summary op in a TensorFlow session.

  Arguments:
    name: A unique name for the generated summary node.
    audio: An `np.array` representing audio data with shape `[k, t, c]`,
      where `k` is the number of audio clips, `t` is the number of
      frames, and `c` is the number of channels. Elements should be
      floating-point values in `[-1.0, 1.0]`.
    sample_rate: An `int` that represents the sample rate, in Hz.
      Must be positive.
    labels: Optional list (or rank-1 `np.array`) of textstrings or UTF-8
      bytestrings whose length is the first dimension of `audio`, where
      `labels[i]` contains arbitrary textual information about
      `audio[i]`. (For instance, this could be some text that a TTS
      system was supposed to produce.) Markdown is supported.
    max_outputs: Optional `int`. At most this many audio clips will be
      emitted. When more than `max_outputs` many clips are provided, the
      first `max_outputs` many clips will be used and the rest silently
      discarded.
    encoding: A constant `str` indicating the desired encoding. You
      can choose any format you like, as long as it's "wav". Please see
      the "API compatibility note" below.
    display_name: Optional name for this summary in TensorBoard, as a
      `str`. Defaults to `name`.
    description: Optional long-form description for this summary, as a
      `str`. Markdown is supported. Defaults to empty.

  Returns:
    A `tf.Summary` protobuf object.

  API compatibility note: The default value of the `encoding`
  argument is _not_ guaranteed to remain unchanged across TensorBoard
  versions. In the future, we will by default encode as FLAC instead of
  as WAV. If the specific format is important to you, please provide a
  file format explicitly.
  """
  audio = np.array(audio)
  if audio.ndim != 3:
    raise ValueError('Shape %r must have rank 3' % (audio.shape,))
  if encoding is None:
    encoding = 'wav'

  if encoding == 'wav':
    encoding = metadata.Encoding.Value('WAV')
    encoder = functools.partial(util.encode_wav,
                                samples_per_second=sample_rate)
  else:
    raise ValueError('Unknown encoding: %r' % encoding)

  limited_audio = audio[:max_outputs]
  if labels is None:
    limited_labels = [b''] * len(limited_audio)
  else:
    limited_labels = [tf.compat.as_bytes(label)
                      for label in labels[:max_outputs]]

  encoded_audio = [encoder(a) for a in limited_audio]
  content = np.array([encoded_audio, limited_labels]).transpose()
  tensor = tf.make_tensor_proto(content, dtype=tf.string)

  if display_name is None:
    display_name = name
  summary_metadata = metadata.create_summary_metadata(
      display_name=display_name,
      description=description,
      encoding=encoding)

  summary = tf.Summary()
  summary.value.add(tag='%s/audio_summary' % name,
                    metadata=summary_metadata,
                    tensor=tensor)
  return summary