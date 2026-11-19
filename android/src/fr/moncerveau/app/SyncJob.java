package fr.moncerveau.app;

import android.app.job.*;

public class SyncJob extends JobService {
  public boolean onStartJob(JobParameters p) {
    Sync.job(this, () -> jobFinished(p, false));
    return true;
  }

  public boolean onStopJob(JobParameters p) {
    return true;
  }
}
