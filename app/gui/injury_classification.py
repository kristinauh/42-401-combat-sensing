from collections import deque

# store data buffers for derivative calculations, collect over a fixed window size
WINDOW_SIZE = 100

# constants for each buffer type
HR_BUF_TAG = 0
SPO2_BUF_TAG = 1
RR_BUF_TAG = 2
SBP_BUF_TAG = 3
DBP_BUF_TAG = 4
MOTION_BUF_TAG = 5
SI_BUF_TAG = 6

# error tolerance for each range of hemothorax and pneumothorax vitals
HEMO_PNEUMO_TOLERANCE = 0.05

# use as reference shock index for soldier (normal range 0.5-0.7)
NORMAL_SI = 0.7
SI_SLOPE = 19
SI_WINDOW_SIZE = 20

LIMP_MOTION_THRESHOLD = 0.2
IMPACT_THRESHOLD = 8

class InjuryClassifier:
    def __init__(self):
        # buffers for most recent data
        self.hr_buf = deque(maxlen=WINDOW_SIZE)
        self.spo2_buf = deque(maxlen=WINDOW_SIZE)
        self.motion_buf = deque(maxlen=WINDOW_SIZE)
        self.rr_buf = deque(maxlen=WINDOW_SIZE)
        self.sbp_buf = deque(maxlen=WINDOW_SIZE)
        self.dbp_buf = deque(maxlen=WINDOW_SIZE)
        self.shock_index_buf = deque(maxlen=WINDOW_SIZE)
        self.impact_buf = deque(maxlen=WINDOW_SIZE)

        # probabilities of various injury
        self.hemorrhage = 0
        self.hemorrhage_bv_loss = 0
        self.hemothorax = 0
        self.pneumothorax = 0
        self.injured_limb = 0
        self.impact_injury = 0

    def update(self, hr, spo2, rr, sbp, dbp, motion_state, imu_impact):
        # add samples to right end of queue (dequeue older samples)
        if hr is not None:
            self.hr_buf.append(hr)
        if spo2 is not None:
            self.spo2_buf.append(spo2)
        if rr is not None:
            self.rr_buf.append(rr)
        if sbp is not None:
            self.sbp_buf.append(sbp)
        if dbp is not None:
            self.dbp_buf.append(dbp)
        if motion_state is not None:
            self.motion_buf.append(motion_state)
        if imu_impact is not None:
            self.impact_buf.append(imu_impact)
        
        # calculate shock index = heart rate / systolic blood pressure
        if (sbp is not None) and (sbp != 0) and (hr is not None):
            self.shock_index_buf.append(hr / sbp)
        
    # calculate averages over windows at specified parts of the buffer
    def calculate_average(self, start_idx, end_idx, buffer_tag):
        match buffer_tag:
            case 0: buf = self.hr_buf
            case 1: buf = self.spo2_buf
            case 2: buf = self.rr_buf
            case 3: buf = self.sbp_buf
            case 4: buf = self.dbp_buf
            case 5: buf = self.motion_buf
            case 6: buf = self.shock_index_buf
            case _: raise ValueError(f"Unknown buffer_tag: {buffer_tag}")
        
        # not enough valid data in the buffer
        if(len(buf) < end_idx):
            return None

        curr_sum = sum(buf[i] for i in range(start_idx, end_idx))
        
        return (curr_sum / (end_idx - start_idx))
            
    # sets predicted blood loss (ml/kg) based on shock index
    # also sets probability of hemorrhage based on SI
    def calculate_hemorrhage(self):
        if(len(self.shock_index_buf) < SI_WINDOW_SIZE):
            return None
        
        avg_si_recent = self.calculate_average(len(self.shock_index_buf) - SI_WINDOW_SIZE, len(self.shock_index_buf), SI_BUF_TAG)
        if(avg_si_recent is not None):
            
            # force curve through origin to avoid mispredicting blood loss when SI is normal
            self.hemorrhage_bv_loss = (avg_si_recent - NORMAL_SI)/(NORMAL_SI) * SI_SLOPE
            hem_tmp = max((avg_si_recent - NORMAL_SI)*5, 0)
            self.hemorrhage = min(hem_tmp, 1)
            return max(0.0, self.hemorrhage_bv_loss) # bv loss should never be negative
        else:
            return None
    
    # calculate probability of pneumothorax
    def calculate_pneumothorax(self):
        if len(self.spo2_buf) < WINDOW_SIZE or len(self.rr_buf) < WINDOW_SIZE:
            return None

        third = WINDOW_SIZE // 3

        spo2_early  = self.calculate_average(0,           third,        SPO2_BUF_TAG)
        spo2_recent = self.calculate_average(third * 2,   WINDOW_SIZE,  SPO2_BUF_TAG)
        rr_early    = self.calculate_average(0,           third,        RR_BUF_TAG)
        rr_recent   = self.calculate_average(third * 2,   WINDOW_SIZE,  RR_BUF_TAG)

        if any(v is None for v in [spo2_early, spo2_recent, rr_early, rr_recent]):
            return None
    
        spo2_drop = spo2_early - spo2_recent   # positive = dropping
        rr_rise   = rr_recent - rr_early       # positive = rising

        # both must be trending in the right direction
        if spo2_drop <= 0 or rr_rise <= 0:
            return 0.0

        # scale against the article's observed ranges:
        # SpO2 dropped 10% (99→89) and RR rose 15 (20→35) over ~10 min
        spo2_score = min(spo2_drop / 10.0, 1.0)
        rr_score   = min(rr_rise  / 15.0, 1.0)

        probability = (spo2_score + rr_score) / 2.0
        self.pneumothorax = probability
        return probability

    # calculate probability of hemothorax
    def calculate_hemothorax(self):
        # hemothorax = pneumothorax pattern + hemorrhage signal
        ptx_prob = self.calculate_pneumothorax()
        if ptx_prob is None or ptx_prob == 0.0:
            return 0.0

        # if SI is also elevated, shift probability toward hemothorax
        avg_si = self.calculate_average(
            len(self.shock_index_buf) - SI_WINDOW_SIZE,
            len(self.shock_index_buf),
            SI_BUF_TAG
        )
        if avg_si is None:
            return ptx_prob * 0.3  # no SI data, low confidence

        si_score = min(max((avg_si - NORMAL_SI) / NORMAL_SI, 0.0), 1.0)
        self.hemothorax = ptx_prob * si_score
        return self.hemothorax


    # calculate probability of a limb injury (fracture,
    # gunshot wound) or explosive blast injury / high fall impact injury
    def calculate_limb_and_impact_injury(self):
        limp_cnt = 0
        motion_cnt = 0
        stationary_cnt = 0
        fall_detected = False
        impact_magnitude = 0
        if(len(self.motion_buf) < 2):
            return None
        
        # count proportion of limp, and other motion events
        for i in range(0, len(self.motion_buf)):
            if(self.motion_buf[i] in ["LIMPING"]):
                limp_cnt = limp_cnt + 1
                motion_cnt = motion_cnt + 1
            if(self.motion_buf[i] in ["WALKING", "RUNNING", "JUMPING", "SQUATTING", "SITTING"]):
                motion_cnt = motion_cnt + 1
            if(self.motion_buf[i] in ["STATIONARY"]):
                stationary_cnt = stationary_cnt + 1
            if(self.motion_buf[i] in ["DETECTED_FALL"]):
                fall_detected = True
                if(i < len(self.impact_buf)):
                    impact_magnitude = self.impact_buf[i]
                else:
                    impact_magnitue = 0.0
                
        if(motion_cnt == 0):
            limp_prop = 0.0
        else:
            limp_prop = float(limp_cnt) / float(motion_cnt)
        
        self.injured_limb = 1.25*(limp_prop - LIMP_MOTION_THRESHOLD)
        self.impact_injury = 0.0 if not fall_detected else 0.125*(impact_magnitude - IMPACT_THRESHOLD)
    
    # main fn to update all injury probabilities
    def calculate_injury_probabilities(self):
        self.calculate_hemorrhage()
        self.calculate_pneumothorax()
        self.calculate_hemothorax()
        self.calculate_limb_and_impact_injury()
        
        return {
            "hemorrhage":         self.hemorrhage,
            "hemorrhage_bv_loss": self.hemorrhage_bv_loss,
            "hemothorax":         self.hemothorax,
            "pneumothorax":       self.pneumothorax,
            "injured_limb":       self.injured_limb,
            "impact_injury":      self.impact_injury,
        }
