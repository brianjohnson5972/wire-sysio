import re
import errno
import subprocess
import time
import os
import platform
from collections import deque
from collections import namedtuple
import inspect
import json
import shlex
import socket
from datetime import datetime
from sys import stdout
from sys import exit
import traceback
import shutil
import sys
from pathlib import Path

# Fancy import to maintain compatibility with python 3.10
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

###########################################################################################

def addEnum(enumClassType, type):
    setattr(enumClassType, type, enumClassType(type))

def unhandledEnumType(type):
    raise RuntimeError("No case defined for type=%s" % (type.type))

class EnumType:

    def __init__(self, type):
        self.type=type

    def __str__(self):
        return self.type


class ReturnType(EnumType):
    pass

addEnum(ReturnType, "raw")
addEnum(ReturnType, "json")

###########################################################################################

class BlockLogAction(EnumType):
    pass

addEnum(BlockLogAction, "make_index")
addEnum(BlockLogAction, "trim")
addEnum(BlockLogAction, "smoke_test")
addEnum(BlockLogAction, "return_blocks")

###########################################################################################
class Utils:
    Debug=False
    FNull = open(os.devnull, 'w')

    testBinPath = Path(__file__).resolve().parents[2] / 'bin'

    SysClientPath=str(testBinPath / "clio")
    MiscSysClientArgs="--no-auto-kiod"

    LeapClientPath=str(testBinPath / "sys-util")

    SysWalletName="kiod"
    SysWalletPath=str(testBinPath / SysWalletName)

    SysServerName="nodeop"
    SysServerPath=str(testBinPath / SysServerName)

    ShuttingDown=False

    FileDivider="================================================================="
    TestLogRoot=f"{str(Path.cwd().resolve())}/TestLogs"
    DataRoot=os.path.basename(sys.argv[0]).rsplit('.',maxsplit=1)[0]
    PID = os.getpid()
    DataPath= f"{TestLogRoot}/{DataRoot}{PID}"
    DataDir=f"{DataPath}/"
    ConfigDir=f"{DataPath}/"

    TimeFmt='%Y-%m-%dT%H:%M:%S.%f'

    @staticmethod
    def timestamp():
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")

    @staticmethod
    def checkOutputFileWrite(time, cmd, output, error):
        stop=Utils.timestamp()
        if not os.path.isdir(Utils.TestLogRoot):
            if Utils.Debug: Utils.Print("TestLogRoot creating dir %s in dir: %s" % (Utils.TestLogRoot, os.getcwd()))
            os.mkdir(Utils.TestLogRoot)
        if not os.path.isdir(Utils.DataPath):
            if Utils.Debug: Utils.Print("DataPath creating dir %s in dir: %s" % (Utils.DataPath, os.getcwd()))
            os.mkdir(Utils.DataPath)
        if not hasattr(Utils, "checkOutputFile"):
            Utils.checkOutputFilename=f"{Utils.DataPath}/subprocess_results.log"
            if Utils.Debug: Utils.Print("opening %s in dir: %s" % (Utils.checkOutputFilename, os.getcwd()))
            Utils.checkOutputFile=open(Utils.checkOutputFilename,"w")
        else:
            Utils.checkOutputFile=open(Utils.checkOutputFilename,"a")

        Utils.checkOutputFile.write(Utils.FileDivider + "\n")
        Utils.checkOutputFile.write("start={%s}\n" % (time))
        Utils.checkOutputFile.write("cmd={%s}\n" % (" ".join(cmd)))
        Utils.checkOutputFile.write("cout={%s}\n" % (output))
        Utils.checkOutputFile.write("cerr={%s}\n" % (error))
        Utils.checkOutputFile.write("stop={%s}\n" % (stop))

    @staticmethod
    def Print(*args, **kwargs):
        stackDepth=len(inspect.stack())-2
        s=' '*stackDepth
        stdout.write(Utils.timestamp() + " ")
        stdout.write(s)
        print(*args, **kwargs)

    SyncStrategy=namedtuple("ChainSyncStrategy", "name id arg")

    SyncNoneTag="none"
    SyncReplayTag="replay"
    SyncResyncTag="resync"
    SyncHardReplayTag="hardReplay"

    SigKillTag="kill"
    SigTermTag="term"

    systemWaitTimeout=90
    irreversibleTimeout=60

    @staticmethod
    def setIrreversibleTimeout(timeout):
        Utils.irreversibleTimeout=timeout

    @staticmethod
    def setSystemWaitTimeout(timeout):
        Utils.systemWaitTimeout=timeout

    @staticmethod
    def getDateString(dt):
        return "%d_%02d_%02d_%02d_%02d_%02d" % (
            dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

    @staticmethod
    def nodeExtensionToName(ext):
        r"""Convert node extension (bios, 0, 1, etc) to node name. """
        prefix="node_"
        if ext == "bios":
            return prefix + ext

        return "node_%02d" % (ext)

    @staticmethod
    def getNodeDataDir(ext, relativeDir=None, trailingSlash=False):
        path=os.path.join(Utils.DataDir, Utils.nodeExtensionToName(ext))
        if relativeDir is not None:
           path=os.path.join(path, relativeDir)
        if trailingSlash:
           path=os.path.join(path, "")
        return path

    @staticmethod
    def rmNodeDataDir(ext, rmState=True, rmBlocks=True, rmStateHist=True):
        if rmState:
            shutil.rmtree(Utils.getNodeDataDir(ext, "state"))
        if rmBlocks:
            shutil.rmtree(Utils.getNodeDataDir(ext, "blocks"))
        if rmStateHist:
            shutil.rmtree(Utils.getNodeDataDir(ext, "state-history"), ignore_errors=True)

    @staticmethod
    def getNodeConfigDir(ext, relativeDir=None, trailingSlash=False):
        path=os.path.join(Utils.ConfigDir, Utils.nodeExtensionToName(ext))
        if relativeDir is not None:
           path=os.path.join(path, relativeDir)
        if trailingSlash:
           path=os.path.join(path, "")
        return path

    @staticmethod
    def getChainStrategies():
        chainSyncStrategies={}

        chainSyncStrategy=Utils.SyncStrategy(Utils.SyncNoneTag, 0, "")
        chainSyncStrategies[chainSyncStrategy.name]=chainSyncStrategy

        chainSyncStrategy=Utils.SyncStrategy(Utils.SyncReplayTag, 1, "--replay-blockchain")
        chainSyncStrategies[chainSyncStrategy.name]=chainSyncStrategy

        chainSyncStrategy=Utils.SyncStrategy(Utils.SyncResyncTag, 2, "--delete-all-blocks")
        chainSyncStrategies[chainSyncStrategy.name]=chainSyncStrategy

        chainSyncStrategy=Utils.SyncStrategy(Utils.SyncHardReplayTag, 3, "--hard-replay-blockchain")
        chainSyncStrategies[chainSyncStrategy.name]=chainSyncStrategy

        return chainSyncStrategies

    @staticmethod
    def checkOutput(cmd, ignoreError=False):
        popen = Utils.delayedCheckOutput(cmd)
        return Utils.checkDelayedOutput(popen, cmd, ignoreError=ignoreError)

    @staticmethod
    def delayedCheckOutput(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
        if (isinstance(cmd, list)):
            popen=subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
        else:
            popen=subprocess.Popen(cmd, stdout=stdout, stderr=stderr, shell=True)
        return popen

    @staticmethod
    def checkDelayedOutput(popen, cmd, ignoreError=False):
        assert isinstance(popen, subprocess.Popen)
        assert isinstance(cmd, (str,list))
        start=Utils.timestamp()
        (output,error)=popen.communicate()
        Utils.checkOutputFileWrite(start, cmd, output, error)
        if popen.returncode != 0 and not ignoreError:
            raise subprocess.CalledProcessError(returncode=popen.returncode, cmd=cmd, output=output, stderr=error)
        return output.decode("utf-8") if popen.returncode == 0 else error.decode("utf-8")

    @staticmethod
    def errorExit(msg="", raw=False, errorCode=1):
        if Utils.ShuttingDown:
            Utils.Print("ERROR:" if not raw else "", " errorExit called during shutdown, ignoring.  msg=", msg)
            return
        Utils.Print("ERROR:" if not raw else "", msg)
        traceback.print_stack(limit=-1)
        exit(errorCode)

    @staticmethod
    def cmdError(name, cmdCode=0):
        msg="FAILURE - %s%s" % (name, ("" if cmdCode == 0 else (" returned error code %d" % cmdCode)))
        Utils.Print(msg)

    @staticmethod
    def waitForObj(lam, timeout=None, sleepTime=1, reporter=None):
        if timeout is None:
            timeout=60

        endTime=time.time()+timeout
        needsNewLine=False
        try:
            while endTime > time.time():
                ret=lam()
                if ret is not None:
                    return ret
                if Utils.Debug:
                    Utils.Print("cmd: sleep %d seconds, remaining time: %d seconds" %
                                (sleepTime, endTime - time.time()))
                else:
                    stdout.write('.')
                    stdout.flush()
                    needsNewLine=True
                if reporter is not None:
                    reporter()
                time.sleep(sleepTime)
            else:
                if timeout == 60:
                    raise RuntimeError('waitForObj reached 60 second timeout')
        finally:
            if needsNewLine:
                Utils.Print()

        return None

    @staticmethod
    def waitForBool(lam, timeout=None, sleepTime=1, reporter=None):
        myLam = lambda: True if lam() else None
        ret=Utils.waitForObj(myLam, timeout, sleepTime, reporter=reporter)
        return False if ret is None else ret

    @staticmethod
    def waitForBoolWithArg(lam, arg, timeout=None, sleepTime=1, reporter=None):
        myLam = lambda: True if lam(arg, timeout) else None
        ret=Utils.waitForObj(myLam, timeout, sleepTime, reporter=reporter)
        return False if ret is None else ret

    @staticmethod
    def filterJsonObjectOrArray(data):
        firstObjIdx=data.find('{')
        lastObjIdx=data.rfind('}')
        firstArrayIdx=data.find('[')
        lastArrayIdx=data.rfind(']')
        if firstArrayIdx==-1 or lastArrayIdx==-1:
            retStr=data[firstObjIdx:lastObjIdx+1]
        elif firstObjIdx==-1 or lastObjIdx==-1:
            retStr=data[firstArrayIdx:lastArrayIdx+1]
        elif lastArrayIdx < lastObjIdx:
            retStr=data[firstObjIdx:lastObjIdx+1]
        else:
            retStr=data[firstArrayIdx:lastArrayIdx+1]
        return retStr

    @staticmethod
    def toJson(retStr, trace=False, silentErrors=True):
        jStr=Utils.filterJsonObjectOrArray(retStr)
        if trace: Utils.Print ("RAW > %s" % (retStr))
        if trace: Utils.Print ("JSON> %s" % (jStr))
        if not jStr:
            msg="Received empty JSON response"
            if not silentErrors:
                Utils.Print ("ERROR: "+ msg)
                Utils.Print ("RAW > %s" % retStr)
            raise TypeError(msg)

        try:
            jsonData=json.loads(jStr)
            return jsonData
        except json.decoder.JSONDecodeError as ex:
            Utils.Print (ex)
            Utils.Print ("RAW > %s" % retStr)
            Utils.Print ("JSON> %s" % jStr)
            raise

    @staticmethod
    def runCmdArrReturnJson(cmdArr, trace=False, silentErrors=True):
        retStr=Utils.checkOutput(cmdArr)
        return Utils.toJson(retStr)

    @staticmethod
    def runCmdReturnStr(cmd, trace=False, ignoreError=False):
        cmdArr=shlex.split(cmd)
        return Utils.runCmdArrReturnStr(cmdArr, ignoreError=ignoreError)

    @staticmethod
    def runCmdArrReturnStr(cmdArr, trace=False, ignoreError=False):
        retStr=Utils.checkOutput(cmdArr, ignoreError=ignoreError)
        if trace: Utils.Print ("RAW > %s" % (retStr))
        return retStr

    @staticmethod
    def runCmdReturnJson(cmd, trace=False, silentErrors=False):
        cmdArr=shlex.split(cmd)
        return Utils.runCmdArrReturnJson(cmdArr, trace=trace, silentErrors=silentErrors)

    @staticmethod
    def processLeapUtilCmd(cmd, cmdDesc, silentErrors=True, exitOnError=False, exitMsg=None):
        cmd="%s %s" % (Utils.LeapClientPath, cmd)
        if Utils.Debug: Utils.Print("cmd: %s" % (cmd))
        if exitMsg is not None:
            exitMsg="Context: " + exitMsg
        else:
            exitMsg=""
        output=None
        start=time.perf_counter()
        try:
            output=Utils.runCmdReturnStr(cmd)

            if Utils.Debug:
                end=time.perf_counter()
                Utils.Print("cmd Duration: %.3f sec" % (end-start))
        except subprocess.CalledProcessError as ex:
            if not silentErrors:
                end=time.perf_counter()
                msg=ex.stderr.decode("utf-8")
                errorMsg="Exception during \"%s\". Exception message: %s.  cmd Duration=%.3f sec. %s" % (cmdDesc, msg, end-start, exitMsg)
                if exitOnError:
                    Utils.cmdError(errorMsg)
                    Utils.errorExit(errorMsg)
                else:
                    Utils.Print("ERROR: %s" % (errorMsg))
            return None

        if exitOnError and output is None:
            Utils.cmdError("could not \"%s\". %s" % (cmdDesc,exitMsg))
            Utils.errorExit("Failed to \"%s\"" % (cmdDesc))

        return output

    @staticmethod
    def arePortsAvailable(ports):
        """Check if specified port (as int) or ports (as set) is/are available for listening on."""
        assert(ports)
        if isinstance(ports, int):
            ports={ports}
        assert(isinstance(ports, set))

        for port in ports:
            if Utils.Debug: Utils.Print("Checking if port %d is available." % (port))
            assert(isinstance(port, int))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                s.bind(("127.0.0.1", port))
            except socket.error as e:
                if e.errno == errno.EADDRINUSE:
                    Utils.Print("ERROR: Port %d is already in use" % (port))
                else:
                    # something else raised the socket.error exception
                    Utils.Print("ERROR: Unknown exception while trying to listen on port %d" % (port))
                    Utils.Print(e)
                return False
            finally:
                s.close()

        return True

    @staticmethod
    def pgrepCmd(serverName):
        # pylint: disable=deprecated-method
        # pgrep differs on different platform (amazonlinux1 and 2 for example). We need to check if pgrep -h has -a available and add that if so:
        try:
            pgrepHelp = re.search('-a', subprocess.Popen("pgrep --help 2>/dev/null", shell=True, stdout=subprocess.PIPE).stdout.read().decode('utf-8'))
            pgrepHelp.group(0) # group() errors if -a is not found, so we don't need to do anything else special here.
            pgrepOpts="-a"
        except AttributeError as error:
            # If no -a, AttributeError: 'NoneType' object has no attribute 'group'
            pgrepOpts="-fl"

        return "pgrep %s %s" % (pgrepOpts, serverName)

    @staticmethod
    def getBlockLog(blockLogLocation, blockLogAction=BlockLogAction.return_blocks, outputFile=None, first=None, last=None, throwException=False, silentErrors=False, exitOnError=False):
        assert(isinstance(blockLogLocation, str))
        outputFileStr=" --output-file %s " % (outputFile) if outputFile is not None else ""
        firstStr=" --first %s " % (first) if first is not None else ""
        lastStr=" --last %s " % (last) if last is not None else ""

        blockLogActionStr=None
        returnType=ReturnType.raw
        if blockLogAction==BlockLogAction.return_blocks:
            blockLogActionStr=" print-log --as-json-array "
            returnType=ReturnType.json
        elif blockLogAction==BlockLogAction.make_index:
            blockLogActionStr=" make-index "
        elif blockLogAction==BlockLogAction.trim:
            blockLogActionStr=" trim-blocklog "
        elif blockLogAction==BlockLogAction.smoke_test:
            blockLogActionStr=" smoke-test "
        else:
            unhandledEnumType(blockLogAction)

        cmd="%s block-log %s --blocks-dir %s  %s%s%s" % (Utils.LeapClientPath, blockLogActionStr, blockLogLocation, outputFileStr, firstStr, lastStr)
        if Utils.Debug: Utils.Print("cmd: %s" % (cmd))
        rtn=None
        try:
            if returnType==ReturnType.json:
                rtn=Utils.runCmdReturnJson(cmd, silentErrors=silentErrors)
            else:
                rtn=Utils.runCmdReturnStr(cmd)
        except subprocess.CalledProcessError as ex:
            if throwException:
                raise
            if not silentErrors:
                msg=ex.stderr.decode("utf-8")
                errorMsg="Exception during \"%s\". %s" % (cmd, msg)
                if exitOnError:
                    Utils.cmdError(errorMsg)
                    Utils.errorExit(errorMsg)
                else:
                    Utils.Print("ERROR: %s" % (errorMsg))
            return None

        if exitOnError and rtn is None:
            Utils.cmdError("could not \"%s\"" % (cmd))
            Utils.errorExit("Failed to \"%s\"" % (cmd))

        return rtn

    @staticmethod
    def compare(obj1,obj2,context):
        type1=type(obj1)
        type2=type(obj2)
        if type1!=type2:
            return "obj1(%s) and obj2(%s) are different types, so cannot be compared, context=%s" % (type1,type2,context)

        if obj1 is None and obj2 is None:
            return None

        typeName=type1.__name__
        if type1 == str or type1 == int or type1 == float or type1 == bool:
            if obj1!=obj2:
                return "obj1=%s and obj2=%s are different (type=%s), context=%s" % (obj1,obj2,typeName,context)
            return None

        if type1 == list:
            len1=len(obj1)
            len2=len(obj2)
            diffSizes=False
            minLen=len1
            if len1!=len2:
                diffSizes=True
                minLen=min([len1,len2])

            for i in range(minLen):
                nextContext=context + "[%d]" % (i)
                ret=Utils.compare(obj1[i],obj2[i], nextContext)
                if ret is not None:
                    return ret

            if diffSizes:
                return "left and right side %s comparison have different sizes %d != %d, context=%s" % (typeName,len1,len2,context)
            return None

        if type1 == dict:
            keys1=sorted(obj1.keys())
            keys2=sorted(obj2.keys())
            len1=len(keys1)
            len2=len(keys2)
            diffSizes=False
            minLen=len1
            if len1!=len2:
                diffSizes=True
                minLen=min([len1,len2])

            for i in range(minLen):
                key=keys1[i]
                nextContext=context + "[\"%s\"]" % (key)
                if key not in obj2:
                    return "right side does not contain key=%s (has %s) that left side does, context=%s" % (key,keys2,context)
                ret=Utils.compare(obj1[key],obj2[key], nextContext)
                if ret is not None:
                    return ret

            if diffSizes:
                return "left and right side %s comparison have different number of keys %d != %d, context=%s" % (typeName,len1,len2,context)

            return None

        return "comparison of %s type is not supported, context=%s" % (typeName,context)

    @staticmethod
    def compareFiles(file1: str, file2: str):
        f1 = open(file1)
        f2 = open(file2)

        i = 0
        same = True
        for line1 in f1:
            i += 1
            for line2 in f2:
                if line1 != line2:
                    if Utils.Debug: Utils.Print("Diff line ", i, ":")
                    if Utils.Debug: Utils.Print("\tFile 1: ", line1)
                    if Utils.Debug: Utils.Print("\tFile 2: ", line2)
                    same = False
                break

        f1.close()
        f2.close()
        return same

    @staticmethod
    def addAmount(assetStr: str, deltaStr: str) -> str:
        asset = assetStr.split()
        if len(asset) != 2:
            return None
        delta = deltaStr.split()
        if len(delta) != 2:
            return None
        if asset[1] != delta[1]:
            return None
        return "{0} {1}".format(round(float(asset[0]) + float(delta[0]), 4), asset[1])

    @staticmethod
    def deduceAmount(assetStr: str, deltaStr: str) -> str:
        asset = assetStr.split()
        if len(asset) != 2:
            return None
        delta = deltaStr.split()
        if len(delta) != 2:
            return None
        if asset[1] != delta[1]:
            return None
        return "{0} {1}".format(round(float(asset[0]) - float(delta[0]), 4), asset[1])

    @staticmethod
    def makeHTTPReqStr(host : str, port : str, api_call : str, body : str, keepAlive=False) -> str:
        hdr = "POST " + api_call + " HTTP/1.1\r\n"
        hdr += f"Host: {host}:{port}\r\n"
        body += "\r\n"
        body_len = len(body)
        hdr +=  f"content-length: {body_len}\r\n"
        hdr +=  "Accept: */*\r\n"
        hdr += "Connection: "
        if keepAlive:
            hdr += "Keep-Alive\r\n"
        else:
            hdr += "Close\r\n"
        hdr += "\r\n"
        return hdr + body

    @staticmethod
    def readSocketData(sock : socket.socket, maxMsgSize : int) -> bytes:
        """Read data from a socket until maxMsgSize is reached or timeout
        Retrusn data as bytes object"""
        sock.settimeout(1)
        moreData = True
        data = None
        bufSize = 64
        while moreData and maxMsgSize > 0:
            try:
                bufSize = min(bufSize, maxMsgSize)
                d = sock.recv(bufSize)
                dataSz = len(d)
                maxMsgSize -= dataSz
                if data is None:
                    data = d
                else:
                    data += d
                moreData = (dataSz == bufSize)
            except Exception as e:
                moreData = False
        return data

    @staticmethod
    def readSocketDataStr(sock : socket.socket, maxMsgSize : int, enc : str) -> str:
        """Read data from a socket until maxMsgSize is reached or timeout
        Retrusn data as decoded string object"""
        data = Utils.readSocketData(sock, maxMsgSize)
        return data.decode(enc)

    @staticmethod
    def getNodeopVersion():
        return os.popen(f"{Utils.SysServerPath} --full-version").read().replace("\n", "")
