
const { Worker } = require('worker_threads');
const path = require('path');

class JobCoordinator {
  constructor(maxParallel = 3) {
    this.maxParallel = maxParallel;
    this.running = new Map();
  }

  async runJob(jobType, data) {
    if (this.running.size >= this.maxParallel) {
      await Promise.race(this.running.values());
    }

    const worker = new Worker(path.join(__dirname, `${jobType}/worker.js`), {
      workerData: data
    });

    const promise = new Promise((resolve, reject) => {
      worker.on('message', resolve);
      worker.on('error', reject);
      worker.on('exit', code => {
        if (code !== 0) reject(new Error(`Worker stopped with code ${code}`));
      });
    });

    this.running.set(worker, promise);
    promise.finally(() => this.running.delete(worker));

    return promise;
  }
}

module.exports = new JobCoordinator();
