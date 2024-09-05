import * as chromeLauncher from 'chrome-launcher';
import lighthouse from 'lighthouse';
import { writeFileSync } from 'fs';

const url = process.argv[2];

async function runLighthouse(url) {
    const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless'] });
    const options = { logLevel: 'info', output: 'json', onlyCategories: ['performance'], port: chrome.port };
    const runnerResult = await lighthouse(url, options);

    // Output the result to stdout
    console.log(JSON.stringify(runnerResult.lhr, null, 2));

    await chrome.kill();
}

runLighthouse(url);
