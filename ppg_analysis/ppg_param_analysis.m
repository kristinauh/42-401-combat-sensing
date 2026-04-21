%% Load data
Tppg = readtable('data/ppg_passive.csv', 'TextType', 'string');

if ~isdatetime(Tppg.timestamp)
    Tppg.timestamp = datetime(Tppg.timestamp, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSS');
end

win_ids = unique(Tppg.window);
num_windows = length(win_ids);

% Parameters
trim_sec = 2.0;
low_cut  = 0.5;
high_cut_max = 3.5;
for k = 1:num_windows
    w_k  = win_ids(k);
    Tw_k = Tppg(Tppg.window == w_k, :);

    if height(Tw_k) < 20
        fprintf('Window %d: too few samples (%d)\n', w_k, height(Tw_k));
        continue;
    end

    ir_raw = double(Tw_k.ir_raw);
    t_k  = seconds(Tw_k.timestamp - Tw_k.timestamp(1));
    dt_k = seconds(diff(Tw_k.timestamp));
    dt_k = dt_k(dt_k > 0);
    if isempty(dt_k)
        fprintf('Window %d: no dt\n', w_k);
        continue;
    end

    fs_k = 1 / median(dt_k);
    fs_all(k) = fs_k;
    fprintf('Window %d: fs=%.1f, samples=%d\n', w_k, fs_k, height(Tw_k));

    high_cut = min(high_cut_max, 0.45 * fs_k);
    if fs_k <= 2 * low_cut || high_cut <= low_cut
        fprintf('  fs too low\n');
        continue;
    end

    ir0 = ir_raw - mean(ir_raw);
    [b, a] = butter(2, [low_cut high_cut] / (fs_k/2), 'bandpass');
    ir_filt = filtfilt(b, a, ir0);
    fprintf('  std(ir_filt)=%.3f\n', std(ir_filt));

    if std(ir_filt) == 0
        fprintf('  filtered signal flat\n');
        continue;
    end

    % ... rest of loop
end

%% Estimate HR for every window

est_hr_all = nan(num_windows, 1);
fs_all     = nan(num_windows, 1);

for k = 1:num_windows
    w_k  = win_ids(k);
    Tw_k = Tppg(Tppg.window == w_k, :);

    if height(Tw_k) < 20
        continue;
    end

    ir_raw = double(Tw_k.ir_raw);

    t_k  = seconds(Tw_k.timestamp - Tw_k.timestamp(1));
    dt_k = seconds(diff(Tw_k.timestamp));
    dt_k = dt_k(dt_k > 0);
    if isempty(dt_k); continue; end

    fs_k = 1 / median(dt_k);
    fs_all(k) = fs_k;

    high_cut = min(high_cut_max, 0.45 * fs_k);
    if fs_k <= 2 * low_cut || high_cut <= low_cut; continue; end

    ir0 = ir_raw - mean(ir_raw);
    if length(ir0) <= 12; continue; end

    [b, a] = butter(2, [low_cut high_cut] / (fs_k/2), 'bandpass');
    ir_filt = filtfilt(b, a, ir0);
    if std(ir_filt) == 0; continue; end

    ir_norm = ir_filt / std(ir_filt);

    start_idx = find(t_k >= trim_sec, 1, 'first');
    if isempty(start_idx); continue; end

    ir_norm_trim = ir_norm(start_idx:end);
    if length(ir_norm_trim) < 3; continue; end

    min_dist = min(round(fs_k * 0.4), length(ir_norm_trim) - 2);
    if min_dist < 1; continue; end

    [~, locs] = findpeaks(ir_norm_trim, 'MinPeakDistance', min_dist);

    if length(locs) >= 2
        ibi = diff(locs) / fs_k;
        est_hr_all(k) = 60 / mean(ibi);
    end
end

%% Print summary table

fprintf('\n%-8s  %-6s  %-12s\n', 'Window', 'fs(Hz)', 'Est HR (bpm)');
fprintf('%s\n', repmat('-', 1, 32));
for k = 1:num_windows
    if isnan(est_hr_all(k))
        fprintf('%-8d  %-6.1f  %s\n', win_ids(k), fs_all(k), 'NaN');
    else
        fprintf('%-8d  %-6.1f  %-12.1f\n', win_ids(k), fs_all(k), est_hr_all(k));
    end
end

%% Plot: estimated HR across all windows

valid_idx = ~isnan(est_hr_all);

figure
plot(win_ids(valid_idx), est_hr_all(valid_idx), 'r-s', 'LineWidth', 1.5, 'MarkerSize', 5)
xlabel('Window')
ylabel('Estimated HR (bpm)')
title('Estimated HR Across Windows (Passive Collection)')
grid on

%% Inspect individual windows

for window = 1:num_windows
    w    = win_ids(window);
    Tw   = Tppg(Tppg.window == w, :);

    if height(Tw) < 20
        fprintf('Window %d: too few samples, skipping\n', w);
        continue;
    end

    t      = seconds(Tw.timestamp - Tw.timestamp(1));
    ir_raw = double(Tw.ir_raw);
    red_raw = double(Tw.red_raw);

    dt = seconds(diff(Tw.timestamp));
    dt = dt(dt > 0);
    fs = 1 / median(dt);

    high_cut = min(high_cut_max, 0.45 * fs);
    if fs <= 2 * low_cut || high_cut <= low_cut
        fprintf('Window %d: fs too low, skipping\n', w);
        continue;
    end

    ir0  = ir_raw  - mean(ir_raw);
    red0 = red_raw - mean(red_raw);

    if length(ir0) <= 12; continue; end

    [b, a] = butter(2, [low_cut high_cut] / (fs/2), 'bandpass');
    ir   = filtfilt(b, a, ir0);
    red  = filtfilt(b, a, red0);

    if std(ir) == 0; continue; end

    ir_norm      = ir  / std(ir);
    red_norm     = red / std(red);
    ir_raw_norm  = ir0 / std(ir0);
    red_raw_norm = red0 / std(red0);

    start_idx = find(t >= trim_sec, 1, 'first');
    if isempty(start_idx); continue; end

    t_trim       = t(start_idx:end);
    ir_trim      = ir(start_idx:end);
    ir_norm_trim = ir_norm(start_idx:end);

    min_dist = min(round(fs * 0.4), length(ir_norm_trim) - 2);
    if min_dist < 1
        pks  = [];
        locs = [];
    else
        [pks, locs] = findpeaks(ir_norm_trim, 'MinPeakDistance', min_dist);
    end

    if length(locs) >= 2
        ibi    = diff(locs) / fs;
        hr_est = 60 / mean(ibi);
    else
        hr_est = NaN;
    end

    % FFT
    N    = length(ir_trim);
    f    = (0:floor(N/2)) * fs / N;
    P_ir = abs(fft(ir_trim) / N);
    P_ir = P_ir(1:floor(N/2)+1);

    % --- Figure: raw vs filtered + FFT ---
    figure('Name', sprintf('Window %d', w))

    subplot(3,1,1)
    plot(t, ir_raw_norm, 'Color', [0.8 0.8 0.8])
    hold on
    plot(t, ir_norm, 'k', 'LineWidth', 1.0)
    if ~isempty(locs)
        plot(t_trim(locs), pks, 'bo', 'MarkerSize', 5)
    end
    xline(trim_sec, '--b', 'Trim')
    xlabel('Time (s)'); ylabel('Norm. Amplitude')
    if isnan(hr_est)
        title(sprintf('IR — Window %d | Est HR: NaN', w))
    else
        title(sprintf('IR — Window %d | Est HR: %.1f bpm', w, hr_est))
    end
    legend('Raw', 'Bandpass', 'Peaks')
    grid on

    subplot(3,1,2)
    plot(t, red_raw_norm, 'Color', [0.8 0.8 0.8])
    hold on
    plot(t, red_norm, 'r', 'LineWidth', 1.0)
    xline(trim_sec, '--b', 'Trim')
    xlabel('Time (s)'); ylabel('Norm. Amplitude')
    title('Red — Raw vs Filtered')
    legend('Raw', 'Bandpass')
    grid on

    subplot(3,1,3)
    plot(f, P_ir, 'k', 'LineWidth', 1.5)
    xlim([0 5])
    xlabel('Frequency (Hz)'); ylabel('Amplitude')
    title('IR FFT Spectrum')
    grid on
end