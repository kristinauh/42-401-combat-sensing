% Test code for checking out the collected data
set(groot, 'defaultTextInterpreter', 'None');

file_name = './data/raw/harry/fall_forward_0.csv';
T0 = readtable(file_name);
dataCols = T0.Properties.VariableNames( ...
    varfun(@isnumeric, T0, 'OutputFormat','uniform') ...
);
D0 = T0{:, dataCols};
idx = [true; any(diff(D0) ~= 0, 2)];

T0 = T0(idx, :);
ts0 = datetime(T0.timestamp, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSS');
time0 = zeros(1, length(ts0));

for i = 2:length(ts0)
    time0(i) = time0(i-1) + T0.MCU_TIME(i);
end

time0 = time0./1000;

figure_name = file_name + "; Sample size: " + size(time0, 2);

figure;
subplot(2,1,1);
hold on;
plot(time0, T0.ASVM);
title("ASVM", figure_name);
hold off;

subplot(2,1,2);
hold on;
plot(time0, T0.GSVM);
title("GSVM", figure_name)
hold off;

%%
BUF_SIZE = 200;
G = 9.81;
IDLE_TRIGGER = 0.85;
CHECK_TRIGGER = 1.4;
DEV_BUFFER_SIZE = 50;
ACCEL_DEV_TRIGGER = 0.2;
GYRO_DEV_TRIGGER = 0.2;
TILT_TRIGGER = 0.3;
INIT_TILT_SIZE = 10;
FINAL_TILT_SIZE = 60;

idle_trigger = find(T0.ASVM <= IDLE_TRIGGER, 1, 'first');

%% test fft lol
Y = fft(T0.ASVM);
fs = 100
f = fs.*time0./60; % hz to bpm
figure;
hold on;
plot(f(1:300), abs(Y(1:300)));
hold off;
%% 
check_trigger_idx = find(T0.ASVM(idle_trigger:end) >= CHECK_TRIGGER, 1, 'first');
check_trigger = idle_trigger + check_trigger_idx - 1;

if (idle_trigger + BUF_SIZE > size(T0.ASVM, 1))
    end_idx = size(T0.ASVM, 1);
else
    end_idx = idle_trigger + BUF_SIZE;
end

fall_sample = T0.ASVM(idle_trigger:end_idx);
fall_sample_g = T0.GSVM(idle_trigger:end_idx);
fall_sample_ax = T0.AX(idle_trigger:end_idx);
fall_sample_ay = T0.AY(idle_trigger:end_idx);
fall_sample_az = T0.AZ(idle_trigger:end_idx);

time_sample = time0(idle_trigger:end_idx);

figure;
hold on;
subplot(3,1,1)
plot(time_sample, fall_sample)
hold on
xline(time_sample(check_trigger_idx))
xline(time_sample(INIT_TILT_SIZE))
xline(time_sample(end - FINAL_TILT_SIZE))
xline(time_sample(end - DEV_BUFFER_SIZE))
title("Sample buffer being processed")
subtitle("accel dev: " + std(fall_sample(end - DEV_BUFFER_SIZE:end)))

subplot(3,1,2)
plot(time_sample, fall_sample_g)
hold on
xline(time_sample(check_trigger_idx))
xline(time_sample(INIT_TILT_SIZE))
xline(time_sample(end - FINAL_TILT_SIZE))
xline(time_sample(end - DEV_BUFFER_SIZE))
subtitle("gyro dev for last 50 samples: " + std(fall_sample_g(end - DEV_BUFFER_SIZE:end)))

hold off;
subplot(3,1,3)
hold on;
plot(time0, T0.ASVM)
xline(time0(check_trigger))
xline(time0(idle_trigger)) 
xline(time0(end_idx))
title("Full Fall Sample")

figure;
subplot(2,1,1)
angle_sample_xy = atan2(T0.AX, T0.AY).*(180/pi);
angle_sample_xz = atan2(T0.AX, T0.AZ).*(180/pi);
angle_sample_yz = atan2(T0.AY, T0.AZ).*(180/pi);

angle_sample_yx = atan2(T0.AY, T0.AX).*(180/pi);
angle_sample_zx = atan2(T0.AZ, T0.AX).*(180/pi);
angle_sample_zy = atan2(T0.AZ, T0.AY).*(180/pi);

xz_dist = sqrt((T0.AX).^2 + (T0.AZ).^2);
horizontal_angle = (atan2(T0.AY, xz_dist)).*(180/pi);

hold on
plot(time0, horizontal_angle);
subtitle(figure_name);
yline(90)
yline(180)
yline(-90)
yline(-180)
xline(time0(check_trigger))
xline(time0(idle_trigger)) 
xline(time0(end_idx))

title("Angles over time throughout sample")

subplot(2,1,2)
plot(time0, T0.ASVM)
hold on
plot(time0, T0.AX)
plot(time0, T0.AY)
plot(time0, T0.AZ)
legend("ASVM", "AX", "AY", "AZ", 'location', 'southeast')
title("ASVM data")