#!/usr/bin/env node
/**
 * E2E test JavaScript ES module hook script for validation.
 *
 * This hook demonstrates ES module syntax (.mjs extension).
 * Validates that .mjs files receive proper node prefix.
 */

import { existsSync } from 'fs';
import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function main() {
    // Read config if provided as first argument
    const configPath = process.argv[2];
    let configLoaded = false;

    if (configPath && existsSync(configPath)) {
        configLoaded = true;
    }

    // Read stdin
    let inputData = '';
    for await (const chunk of process.stdin) {
        inputData += chunk;
    }

    let event = {};
    try {
        event = inputData.trim() ? JSON.parse(inputData) : {};
    } catch (e) {
        event = {};
    }

    const result = {
        continue: true,
        message: 'E2E JavaScript ES module hook (.mjs) executed successfully',
        runtime: 'node',
        module_type: 'esm',
        config_loaded: configLoaded,
        event_type: event.type || 'unknown',
    };

    console.log(JSON.stringify(result));
}

main().catch(console.error);
