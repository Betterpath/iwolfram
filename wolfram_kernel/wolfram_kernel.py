from __future__ import print_function

from metakernel import MetaKernel, ProcessMetaKernel, REPLWrapper, u
from IPython.display import Image, SVG
from IPython.display import Latex, HTML
from IPython.display import Audio

import subprocess
import os
import sys
import tempfile

__version__ = '0.0.0'

try:
    from .config import mathexec
except Exception:
    mathexec = "mathics"




class WolframKernel(ProcessMetaKernel):
    implementation = 'Wolfram Mathematica Kernel'
    implementation_version = __version__,
    language = 'mathematica'
    language_version = '10.0',
    banner = "Wolfram Mathematica Kernel"
    language_info = {
        'exec': mathexec,
        'mimetype': 'text/x-mathics',
        'name': 'wolfram_kernel',
        'file_extension': '.m',
        'help_links': MetaKernel.help_links,
    }

    kernel_json = {
        'argv': [ sys.executable, '-m', 'wolfram_kernel', '-f', '{connection_file}'],
        'display_name': 'Wolfram Mathematica',
        'language': 'mathematica',
        'name': 'wolfram_kernel'
    }
    def get_usage(self):
        return "This is the Wolfram Mathematica kernel."

    def repr(self, data):
        return data

    _initstringwolfram = """
$PrePrint:=Module[{fn,res,texstr}, 
If[#1 === Null, res=\"null:\",

Switch[Head[#1],
          String,
            res=\"string:\"<>#1,
          Graphics,            
            fn=\"{sessiondir}/session-figure\"<>ToString[$Line]<>\".svg\";
            Export[fn,#1,"SVG"];
            res=\"svg:\"<>fn<>\":\"<>\"- graphics -\",
          Graphics3D,            
            fn=\"{sessiondir}/session-figure\"<>ToString[$Line]<>\".jpg\";
            Export[fn,#1,"JPG"];
            res=\"image:\"<>fn<>\":\"<>\"- graphics3d -\",
          Sound,
            fn=\"{sessiondir}/session-sound\"<>ToString[$Line]<>\".wav\";
            Export[fn,#1,"wav"];
            res=\"sound:\"<>fn<>\":\"<>\"- sound -\",
          _,            
            texstr=StringReplace[ToString[TeXForm[#1]],\"\\n\"->\" \"];
            res=\"tex:\"<>ToString[StringLength[texstr]]<>\":\"<> texstr<>\":\"<>ToString[InputForm[#1]]
       ]
       ];
       res
    ]&;
$DisplayFunction=Identity;
"""


    _initstringmathics = """
System`$OutputSizeLimit=1000000000000
$PrePrint:=Module[{fn,res,mathmlstr}, 
If[#1 === Null, res=\"null:\",

Switch[Head[#1],
          String,
            res=\"string:\"<>#1,
          _,            
            mathmlstr=ToString[MathMLForm[#1]];
            res=\"mathml:\"<>ToString[StringLength[mathmlstr]]<>\":\"<> mathmlstr<>\":\"<>ToString[InputForm[#1]]
       ]
       ];
       res
    ]&;
$DisplayFunction=Identity;
"""

    _session_dir = ""
    _first = True
    initfilename = ""
    _banner = None

    @property
    def banner(self):
        if self._banner is None:
            banner = "mathics 0.1"
            self._banner = u(banner)
        return self._banner

    def check_wolfram(self):
        starttext = os.popen("bash -c 'echo |" +  self.language_info['exec']  +"'").read()
        if starttext[:11] == "Mathematica":			      
            self.is_wolfram = True
        else:
            self.is_wolfram = False
        return self.is_wolfram
            

    def build_initfile(self):
        if self.is_wolfram:
            self._initstring = self._initstringwolfram
        else:
            self._initstring = self._initstringmathics
        self._first = True
        self._session_dir = tempfile.mkdtemp()
        self._initstring = self._initstring.replace("{sessiondir}", self._session_dir)
        self.initfilename = self._session_dir + '/init.m'
        print(self.initfilename)
        f = open(self.initfilename, 'w')
        f.write(self._initstring)
        f.close()
        

    def makeWrapper(self):
        """
	Start a math/mathics kernel and return a :class:`REPLWrapper` object.
        """

        orig_prompt = u('In\[.*\]:=')
        prompt_cmd = None
        change_prompt = None
        self.check_wolfram()
        self.build_initfile()
        
        if not self.is_wolfram:
            cmdline = self.language_info['exec'] + " --colors NOCOLOR --persist '" +  self.initfilename + "'"
        else:
            cmdline = self.language_info['exec'] + " -initfile '"+ self.initfilename+"'"
        replwrapper = REPLWrapper(cmdline, orig_prompt, change_prompt,
                                  prompt_emit_cmd=prompt_cmd, echo=True)
        return replwrapper

    def do_execute_direct(self, code):
        jscode="""
           if(typeof document.getElementsByID("graphics3dScript")[0] == 'undefined'){
               var tagg = document.createElement('script');
               tagg.type = "text/javascript";
               tagg.src = "/static/js/graphics3d.js";
               tagg.charset = 'utf-8';
               tagg.id = "graphics3dScript"
               document.getElementsByTagName("head")[0].appendChild( tagg );
               //alert("library loaded");
          }
        """

        #self.Display(Javascript(jscode))

        # Processing multiline code
        codelines = code.splitlines()
        lastline = ""
        resp = ""
        for codeline in codelines:
            if codeline.strip() == "":
                lastline = lastline.strip()
                if lastline == "":
                    continue
                if resp.strip() != "":
                    print(resp)
                resp = self.do_execute_direct(lastline)
                lastline = ""
                continue
            lastline = lastline + codeline
        code = lastline.strip()
        if code == "":
            return resp
        else:
            if resp != "":
                print(resp)
        # Processing last valid line
        ##
        ## TODO: Implement the functionality of PrePrint in mathics. It would fix also the call for %# as part of expressions.
        ##
        if not self.is_wolfram:        
            code = "$PrePrint[" + code + "]"

        resp = super(WolframKernel, self).do_execute_direct(code)
        lineresponse = resp.output.splitlines()
        outputfound = False
        mmaexeccount = -1
        if self.is_wolfram:
            for linnum, liner in enumerate(lineresponse):
                if not outputfound and liner[:4] == "Out[":
                    outputfound = True
                    for pos in range(len(liner) - 4):
                        if liner[pos + 4] == ']':
                            mmaexeccount = int(liner[4:(pos + 4)]) - 1
                            outputtext = liner[(pos + 7):]
                            break
                        continue
                elif outputfound:
                    if liner == u' ':
                        if outputtext[-1] == '\\':  # and lineresponse[linnum + 1] == '>':
                            outputtext = outputtext[:-1]
                            lineresponse[linnum + 1] = lineresponse[linnum + 1][4:]
                            continue
                    outputtext = outputtext + liner
                else:
                    print(liner)
        else:
            for linnum, liner in enumerate(lineresponse):
                if not outputfound and liner[:4] == "Out[":
                    outputfound = True
                    for pos in range(len(liner) - 4):
                        if liner[pos + 4] == ']':
                            mmaexeccount = int(liner[4:(pos + 4)]) - 1
                            outputtext = liner[(pos + 7):]
                            break
                        continue
                elif outputfound:
                    if liner == u' ':
                        if outputtext[-1] == '\\':  # and lineresponse[linnum + 1] == '>':
                            outputtext = outputtext[:-1]
                            lineresponse[linnum + 1] = lineresponse[linnum + 1][4:]
                            continue
                    outputtext = outputtext + liner[7:]
                else:
                    print(liner)

        if  mmaexeccount>0:
            self.execution_count = mmaexeccount
        


        if(outputtext[:5] == 'null:'):
            return ""
        if (outputtext[:7] == 'string:'):
            return outputtext[7:]
        if (outputtext[:7] == 'mathml:'):
            for p in range(len(outputtext) - 7):
                pp = p + 7
                if outputtext[pp] == ':':
                    lentex = int(outputtext[7:pp])
                    self.Display(HTML(outputtext[(pp + 1):(pp + lentex + 1)]))
                    return outputtext[(pp + lentex + 2):]
        if (outputtext[:4] == 'tex:'):
            for p in range(len(outputtext) - 4):
                pp = p + 4
                if outputtext[pp] == ':':
                    lentex = int(outputtext[4:pp])
                    self.Display(Latex('$' + outputtext[(pp + 1):(pp + lentex + 1)] + '$'))
                    return outputtext[(pp + lentex + 2):]

        if(outputtext[:4] == 'svg:'):
            for p in range(len(outputtext) - 4):
                pp = p + 4
                if outputtext[pp] == ':':
                    self.Display(SVG(outputtext[4:pp]))
                    return outputtext[(pp + 1):]

        if(outputtext[:6] == 'image:'):
            for p in range(len(outputtext) - 6):
                pp = p + 6
                if outputtext[pp] == ':':
                    print(outputtext[6:pp])
                    self.Display(Image(outputtext[6:pp]))
                    return outputtext[(pp + 1):]
        if(outputtext[:6] == 'sound:'):
            for p in range(len(outputtext) - 6):
                pp = p + 6
                if outputtext[pp] == ':':
                    self.Display(Audio(url=outputtext[6:pp], autoplay=False, embed=True))
                    return outputtext[(pp + 1):]


    def get_kernel_help_on(self, info, level=0, none_on_fail=False):
        obj = info.get('help_obj', '')
        if not obj or len(obj.split()) > 1:
            if none_on_fail:
                return None
            else:
                return ""
        resp = self.do_execute_direct('? %s' % obj)
        return resp

    def get_completions(self, info):
        """
        Get completions from kernel based on info dict.
        """
        resp = ""
        return resp

    def handle_plot_settings(self):
        pass

    def _make_figs(self, plot_dir):
        pass

if __name__ == '__main__':
#    from ipykernel.kernelapp import IPKernelApp
#    IPKernelApp.launch_instance(kernel_class=MathicsKernel)
    WolframKernel.run_as_main()
