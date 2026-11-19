// audio-processor.js — AudioWorklet processor for voice scribe
// Ported verbatim from legacy voice blueprint.

/**
 * An AudioWorkletProcessor that forwards raw audio data from the first channel
 * of the first input to the main thread via message posting.
 */
class AudioProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super(options);
    }

    /**
     * Called by the system to process audio data.
     * @param {Float32Array[][]} inputs
     * @param {Float32Array[][]} outputs
     * @param {Record<string, Float32Array>} parameters
     * @returns {boolean} Return true to keep the processor alive.
     */
    process(inputs, outputs, parameters) {
        const inputChannelData = inputs[0]?.[0];
        if (!inputChannelData || inputChannelData.length === 0) {
            return true;
        }
        this.port.postMessage(inputChannelData);
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);
