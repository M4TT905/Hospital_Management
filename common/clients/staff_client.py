import sys
import os

# Add the generated_python folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../xcode-build/generated_python")))

# grpc import
import grpc
from datetime import datetime
from typing import Optional

# Common.proto
import Common_pb2 as cpb
import Common_pb2_grpc as cgrpc

# StaffManagement.proto
import StaffManagement_pb2 as spb
import StaffManagement_pb2_grpc as sgrpc

# Victor

# Check proto file to see what the proto objects have as internal datatypes
# Reference the related Cpp source file to see what is actually used by the client

class ansi:
    reset    = "\033[0m"
    bold     = "\033[1m"
    cyan     = "\033[36m"
    green    = "\033[32m"
    red      = "\033[31m"
    magenta  = "\033[35m"
    yellow   = "\033[33m"
    bblue    = "\033[1;34m"
    bcyan    = "\033[1;36m"
    byellow  = "\033[1;33m"
    bmagenta = "\033[1;35m"
    bgreen   = "\033[1;32m"

def timestamp():
    return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "

def print_status_code(status):
    print(f"{ansi.red}[ERROR] gRPC call failed: {status.code()} - {status.details()}{ansi.reset}")


class StaffManagementClient:
    def __init__(self, target: str):
        self.target_hostport = target
        self.channel = grpc.insecure_channel(self.target_hostport)
        self.stub   = sgrpc.StaffManagementStub(self.channel)
        self.common = cgrpc.CommonStub(self.channel)
        self.name   = "staff_client"

    # Common calls

    def ping(self, service_name: str) -> bool:
        request = cpb.Nothing()
        try:
            self.common.ping(request, metadata=[('service-name', service_name)])
            return True
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    def print_service(self, service_name: str) -> bool:
        request = cpb.Nothing()
        try:
            self.common.print(request, metadata=[('service-name', service_name)])
            return True
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    def update(self, service_name: str) -> bool:
        request = cpb.Nothing()
        try:
            self.common.update(request, metadata=[('service-name', service_name)])
            return True
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    #  Staff management 

    def addStaff(self, first: str, middle: str, last: str, sex: str,
                 position: str, salary: float, clearance: str,
                 service_name: str) -> bool:
        staff_dto = spb.StaffDTO(
            staff_name   = cpb.NameDTO(first=first, middle=middle, last=last),
            staff_sex    = sex,
            staff_pos    = position,
            staff_salary = salary,
            staff_clear  = clearance
        )
        try:
            result = self.stub.AddStaff(staff_dto, metadata=[('service-name', service_name)])
            return result.successful
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    def removeStaff(self, staff_id: int, service_name: str) -> bool:
        staff_dto = spb.StaffDTO(staff_id=staff_id)
        try:
            result = self.stub.RemoveStaff(staff_dto, metadata=[('service-name', service_name)])
            return result.successful
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    def changePosition(self, staff_id: int, new_position: str, service_name: str) -> bool:
        staff_dto = spb.StaffDTO(staff_id=staff_id, staff_pos=new_position)
        try:
            result = self.stub.ChangePosition(staff_dto, metadata=[('service-name', service_name)])
            return result.successful
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    def changeClearance(self, staff_id: int, new_clearance: str, service_name: str) -> bool:
        staff_dto = spb.StaffDTO(staff_id=staff_id, staff_clear=new_clearance)
        try:
            result = self.stub.ChangeClearance(staff_dto, metadata=[('service-name', service_name)])
            return result.successful
        except grpc.RpcError as e:
            print_status_code(e)
            return False

    # Staff information

    def getInfo(self, staff_id: int, service_name: str) -> Optional[dict]:
        staff_dto = spb.StaffDTO(staff_id=staff_id)
        try:
            r = self.stub.SeeStaffInformation(staff_dto, metadata=[('service-name', service_name)])
            return {
                "staff_id" : r.staff_id,
                "name"     : f"{r.staff_name.first} {r.staff_name.last}",
                "sex"      : r.staff_sex,
                "position" : r.staff_pos,
                "salary"   : r.staff_salary,
                "clearance": r.staff_clear,
                "room"     : r.staff_room
            }
        except grpc.RpcError as e:
            print_status_code(e)
            return None

    # Scheduling 

    def getTodaysSchedule(self, staff_id: int, service_name: str) -> dict:
        staff_dto = spb.StaffDTO(staff_id=staff_id)
        try:
            result = self.stub.SeeTodaysSchedule(staff_dto, metadata=[('service-name', service_name)])
            return {"shifts": self._parse_schedule(result)}
        except grpc.RpcError as e:
            print_status_code(e)
            return {"shifts": []}

    def getTomorrowsSchedule(self, staff_id: int, service_name: str) -> dict:
        staff_dto = spb.StaffDTO(staff_id=staff_id)
        try:
            result = self.stub.SeeTomorrowsSchedule(staff_dto, metadata=[('service-name', service_name)])
            return {"shifts": self._parse_schedule(result)}
        except grpc.RpcError as e:
            print_status_code(e)
            return {"shifts": []}

    def _parse_schedule(self, schedule_proto) -> list:
        shifts = []
        for s in schedule_proto.shifts:
            shift = s.shift
            start = shift.start
            shifts.append({
                "staff_id"    : s.staff.staff_id,
                "room_id"     : shift.room_id,
                "start"       : f"{start.year}-{start.month:02d}-{start.day:02d} "
                                f"{start.time.hour:02d}:{start.time.minute:02d}",
                "duration_hrs": shift.duration
            })
        return shifts