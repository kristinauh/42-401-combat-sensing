from collections import deque

# store data buffers for derivative calculations, collect over a fixed window size
WINDOW_SIZE = 100

# constants for each buffer type
HR_BUF_TAG = 0
SPO2_BUF_TAG = 1
RR_BUF_TAG = 2
SP_BUF_TAG = 3
DP_BUF_TAG = 4
MOTION_BUF_TAG = 5
SI_BUF_TAG = 6

# use as reference shock index for soldier (normal range 0.5-0.7)
NORMAL_SI = 0.7
SI_SLOPE = 19
SI_WINDOW_SIZE = 20

class InjuryClassifier:
    def __init__(self):
        # buffers for most recent data
        self.hr_buf = deque(maxlen=WINDOW_SIZE)
        self.spo2_buf = deque(maxlen=WINDOW_SIZE)
        self.motion_buf = deque(maxlen=WINDOW_SIZE)
        self.rr_buf = deque(maxlen=WINDOW_SIZE)
        self.sp_buf = deque(maxlen=WINDOW_SIZE)
        self.dp_buf = deque(maxlen=WINDOW_SIZE)
        self.shock_index_buf = deque(maxlen=WINDOW_SIZE)

        # probabilities of various injury
        self.hemorrhage = 0
        self.hemorrhage_bv_loss = 0
        self.hemothorax = 0
        self.pneumothorax = 0
        self.injured_limb = 0
        self.high_blast = 0

    def update(self, hr, spo2, rr, sp, dp, motion_state):
        # add samples to right end of queue (dequeue older samples)
        if hr is not None:
            self.hr_buf.append(hr)
        if spo2 is not None:
            self.spo2_buf.append(spo2)
        if rr is not None:
            self.rr_buf.append(rr)
        if sp is not None:
            self.sp_buf.append(sp)
        if dp is not None:
            self.dp_buf.append(dp)
        if motion_state is not None:
            self.motion_buf.append(motion_state)
        
        # calculate shock index = heart rate / systolic blood pressure
        if (sp is not None) and (sp != 0) and (hr is not None):
            self.shock_index_buf.append(hr / sp)
        
    # calculate averages over windows at specified parts of the buffer
    def calculate_average(self, start_idx, end_idx, buffer_tag):
        match buffer_tag:
            case 0: buf = self.hr_buf
            case 1: buf = self.spo2_buf
            case 2: buf = self.rr_buf
            case 3: buf = self.sp_buf
            case 4: buf = self.dp_buf
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
            return max(0.0, self.hemorrhage_bv_loss)
        else:
            return None
        
    # calculate probability of hemothorax
    def calculate_hemothorax(self):
        pass
    
    # calculate probability of pneumothorax
    def calculate_pneumothorax(self):
        pass
    
    # calculate probability of a limb injury (fracture,
    # gunshot wound) or explosive blast injury
    def calculate_limb_and_blast_injury(self):
        pass
    
    # main fn to update all injury probabilities
    def calculate_injury_probabilities(self):
        self.calculate_hemorrhage()
        self.calculate_hemothorax()
        self.calculate_limb_and_blast_injury()
        self.calculate_pneumothorax()