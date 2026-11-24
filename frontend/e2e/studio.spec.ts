import { expect, test, type Page } from "@playwright/test";

const MOCK_ANALYSIS = {
  visual_summary_hebrew: "הסרטון מציג טיפול פנים דינמי עם חיתוכים מהירים ופרטים אסתטיים.",
  segments: [
    { start_time: 1.0, end_time: 2.5, action_description: "מריחת מסכה" },
    { start_time: 4.0, end_time: 6.0, action_description: "מכשיר על הלחי" },
  ],
};

const MOCK_GENERATE = {
  status: "success",
  video_path: "D:/ClinicStudio/outputs/reel_test.mp4",
  filename: "reel_test.mp4",
  video_url: "/outputs/reel_test.mp4",
  duration: 3.5,
  copywriting: {
    on_screen_hook: "עור זוהר תוך דקות",
    caption: "טיפול מרענן שמעניק זוהר טבעי לעור.",
    call_to_action: "הזמינו תור עוד היום",
    hashtags: ["#קליניקה", "#טיפוח_עור"],
  },
};

async function mockJob(page: Page, jobId: string, result: unknown) {
  await page.route(`**/api/jobs/${jobId}`, async (route) => {
    await route.fulfill({
      json: { job_id: jobId, status: "completed", result, error: null },
    });
  });
}

async function mockAnalyze(page: Page) {
  await page.route("**/api/reels/analyze", async (route) => {
    await route.fulfill({
      status: 202,
      json: { job_id: "job-analyze", status: "queued" },
    });
  });
  await mockJob(page, "job-analyze", MOCK_ANALYSIS);
}

async function mockGenerate(page: Page) {
  await page.route("**/api/reels/generate", async (route) => {
    await route.fulfill({
      status: 202,
      json: { job_id: "job-generate", status: "queued" },
    });
  });
  await mockJob(page, "job-generate", MOCK_GENERATE);
}

async function mockRawClips(page: Page) {
  await page.route("**/api/raw-clips", async (route) => {
    await route.fulfill({ json: [] });
  });
}

async function analyzeFootage(page: Page) {
  await page.goto("/");
  await page.getByTestId("toggle-manual-source").click();
  await page.getByTestId("source-path-input").fill("references/treatment_flow/clip.mp4");
  await page.getByTestId("analyze-button").click();
  await expect(page.getByTestId("visual-summary")).toBeVisible();
}

test("initial state displays source input and analyze button", async ({ page }) => {
  await mockRawClips(page);
  await page.goto("/");

  await expect(page.getByTestId("upload-button")).toBeVisible();
  await expect(page.getByTestId("toggle-manual-source")).toBeVisible();

  await expect(page.getByTestId("source-path-input")).toHaveCount(0);
  await page.getByTestId("toggle-manual-source").click();
  await expect(page.getByTestId("source-path-input")).toBeVisible();

  await expect(page.getByTestId("analyze-button")).toBeVisible();
  await expect(page.getByTestId("visual-summary")).toHaveCount(0);
  await expect(page.getByTestId("segment-start-0")).toHaveCount(0);
});

test("analyzing footage renders the Hebrew summary and editable segment fields", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);
  await analyzeFootage(page);

  const summary = page.getByTestId("visual-summary");
  await expect(summary).toHaveAttribute("dir", "rtl");
  await expect(summary).toContainText(MOCK_ANALYSIS.visual_summary_hebrew);

  await expect(page.getByTestId("segment-start-0")).toHaveValue("1");
  await expect(page.getByTestId("segment-end-0")).toHaveValue("2.5");
  await expect(page.getByTestId("segment-action-0")).toHaveValue("מריחת מסכה");
  await expect(page.getByTestId("segment-start-1")).toHaveValue("4");
  await expect(page.getByTestId("segment-delete-0")).toBeVisible();
});

test("editing a segment start time is sent in the generate payload", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);

  let generateRequestBody:
    | { segments?: { start_time: number; end_time: number; action_description: string }[]; visual_summary?: string }
    | undefined;
  await page.route("**/api/reels/generate", async (route) => {
    generateRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      json: { job_id: "job-generate", status: "queued" },
    });
  });
  await mockJob(page, "job-generate", MOCK_GENERATE);

  await analyzeFootage(page);
  await page.getByTestId("segment-start-0").fill("1.5");
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();

  await expect(page.getByTestId("result-section")).toBeVisible();
  const video = page.locator("video");
  await expect(video).toHaveAttribute("preload", "metadata");
  await expect(video).toHaveAttribute("controls", "");
  expect(await video.evaluate((el: HTMLVideoElement) => el.playsInline)).toBe(true);
  expect(generateRequestBody?.segments?.[0]?.start_time).toBe(1.5);
  expect(generateRequestBody?.segments?.[1]?.action_description).toBe("מכשיר על הלחי");
  expect(generateRequestBody?.visual_summary).toBe(MOCK_ANALYSIS.visual_summary_hebrew);
});

test("analyze keeps polling while the job is still running", async ({ page }) => {
  await mockRawClips(page);
  let polls = 0;
  await page.route("**/api/reels/analyze", async (route) => {
    await route.fulfill({
      status: 202,
      json: { job_id: "job-running", status: "queued" },
    });
  });
  await page.route("**/api/jobs/job-running", async (route) => {
    polls += 1;
    if (polls === 1) {
      await route.fulfill({
        json: { job_id: "job-running", status: "running", result: null, error: null },
      });
      return;
    }
    await route.fulfill({
      json: { job_id: "job-running", status: "completed", result: MOCK_ANALYSIS, error: null },
    });
  });

  await page.goto("/");
  await page.getByTestId("toggle-manual-source").click();
  await page.getByTestId("source-path-input").fill("references/treatment_flow/clip.mp4");
  await page.getByTestId("analyze-button").click();
  await expect(page.getByTestId("analyze-job-status")).toContainText("הניתוח רץ");
  await expect(page.getByTestId("visual-summary")).toBeVisible();
  expect(polls).toBeGreaterThan(1);
});

test("a failed generate job shows the error and re-enables the button", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);
  await page.route("**/api/reels/generate", async (route) => {
    await route.fulfill({
      status: 202,
      json: { job_id: "job-fail", status: "queued" },
    });
  });
  await page.route("**/api/jobs/job-fail", async (route) => {
    await route.fulfill({
      json: {
        job_id: "job-fail",
        status: "failed",
        result: null,
        error: "הרכבת הווידאו נכשלה",
      },
    });
  });

  await analyzeFootage(page);
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();

  await expect(page.getByText("הרכבת הווידאו נכשלה")).toBeVisible();
  await expect(page.getByTestId("generate-button")).toBeEnabled();
  await expect(page.getByTestId("result-section")).toHaveCount(0);
});

test("selecting a video file uploads it with a progress percent and then analyzes", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);

  const mockUploadResponse = {
    filename: "20261008_230000_abcd1234_clip.mp4",
    file_path: "raw_clips/20261008_230000_abcd1234_clip.mp4",
    size_mb: 4.2,
  };
  let releaseUpload: () => void = () => {};
  const uploadHeld = new Promise<void>((resolve) => {
    releaseUpload = resolve;
  });
  let uploadReceived = false;
  await page.route("**/api/upload", async (route) => {
    uploadReceived = true;
    await uploadHeld;
    await route.fulfill({ json: mockUploadResponse });
  });

  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles({
    name: "clip.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("fake-mp4-bytes-for-testing"),
  });

  await expect(page.getByTestId("upload-progress")).toContainText("%");
  releaseUpload();

  await expect(page.getByTestId("visual-summary")).toBeVisible();
  await expect(page.getByTestId("segment-action-0")).toHaveValue("מריחת מסכה");
  expect(uploadReceived).toBe(true);
  await expect(page.getByText(mockUploadResponse.file_path)).toBeVisible();
});

test("copy caption uses the clipboard in a secure context", async ({ page }) => {
  await mockRawClips(page);
  await mockAnalyze(page);
  await mockGenerate(page);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

  await analyzeFootage(page);
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();
  await expect(page.getByTestId("result-section")).toBeVisible();

  await page.getByTestId("copy-caption").click();
  await expect(page.getByTestId("copy-caption")).toContainText("הועתק");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toBe(MOCK_GENERATE.copywriting.caption);
});

test("copy caption falls back to execCommand when clipboard is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      get() {
        return undefined;
      },
    });
    document.execCommand = (command: string) => {
      if (command === "copy") {
        const active = document.activeElement as HTMLTextAreaElement | null;
        (window as unknown as { __copiedText?: string }).__copiedText = active?.value ?? "";
        return true;
      }
      return false;
    };
  });
  await mockRawClips(page);
  await mockAnalyze(page);
  await mockGenerate(page);

  await analyzeFootage(page);
  await page.getByTestId("treatment-input").fill("טיפול מזותרפיה");
  await page.getByTestId("generate-button").click();
  await expect(page.getByTestId("result-section")).toBeVisible();

  await page.getByTestId("copy-caption").click();
  await expect(page.getByTestId("copy-caption")).toContainText("הועתק");
  const copied = await page.evaluate(
    () => (window as unknown as { __copiedText?: string }).__copiedText,
  );
  expect(copied).toBe(MOCK_GENERATE.copywriting.caption);
});
