#!/usr/bin/env node
/**
 * E2E test JavaScript CommonJS hook script for validation.
 *
 * This hook demonstrates CommonJS syntax (.cjs extension).
 * Validates that .cjs files receive proper node prefix.
 */

'use strict';

function main() {
    let inputData = '';

    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', () => {
        let chunk;
        while ((chunk = process.stdin.read()) !== null) {
            inputData += chunk;
        }
    });

    process.stdin.on('end', () => {
        let event = {};
        try {
            event = inputData.trim() ? JSON.parse(inputData) : {};
        } catch (e) {
            event = {};
        }

        const result = {
            continue: true,
            message: 'E2E JavaScript CommonJS hook (.cjs) executed successfully',
            runtime: 'node',
            module_type: 'commonjs',
            event_type: event.type || 'unknown',
        };

        console.log(JSON.stringify(result));
    });
}

main();
