import sys
import os
import re
import gzip
import zlib

from Bio import SeqIO
import scipy
import requests
import pandas as pd



class MetaFile(object):
    """metadata table file object class
    """
    
    def __init__(self, fileName=None, fileObject=None, 
                 stages=None, **pandas_kwargs):
        """Loading file as pandas dataFrame. Checking for necessary columns
        
        Kwargs:
        seqDB -- datafile type: 'MGRAST' or 'SRA'
        stages -- mg-rast processing stage for downloading files. If multiple stages provided,
          will try each in succession until an entry is returned.
        """

        # attributes
        self.fileName = fileName
        self.fileObject = fileObject
        try:
            self.stages = [str(x) for x in stages]
        except TypeError:
            self.stages = None
        self.pd_kwargs = pandas_kwargs

        # loading MetaFile file
        self.loadFile()        


    def loadFile(self):        
        """Loading file as pandas DataFrame """
        if self.fileName is not None:
            self._tbl = pd.read_csv(self.fileName, **self.pd_kwargs)
        elif self.fileObject is not None:            
            self._tbl = pd.read_csv(self.fileObject, **self.pd_kwargs)
        else:
            raise IOError( 'Provide either fileName or fileObject' )

    @classmethod
    def gunzip(cls, inFile, outFile=None):
        """gunzip of a provided file"""
        if outFile is None:
            outFile, ext = os.path.splitext(inFile)
        print outFile

    def getReadStats(self, fileName, fileFormat='fasta'):
        """Loading read file and getting stats:
        Length distribution: min, max, mean, median, stdev
        
        Output:
        readStats attribute -- dict of stats (eg., 'mean' : mean_value)
        """

        seqLens = []
        for seq_record in SeqIO.parse(fileName, fileFormat):
            seqLens.append( len(seq_record) )
        self.readStats = { 
            'min' : scipy.min(seqLens),
            'mean' : scipy.mean(seqLens),
            'median' : scipy.median(seqLens),
            'max' : scipy.max(seqLens),
            'stdev' : scipy.std(seqLens)
            }
            

class MetaFile_MGRAST(MetaFile):
    """Subclass of MetaFile class for importing mgrast metafile """

    def __init__(self, fileName=None, fileObject=None, 
                 stages=[150, 100], **pandas_kwargs):
        MetaFile.__init__(self, fileName=fileName, fileObject=fileObject, 
                          stages=stages, **pandas_kwargs)
        self.checkFile()
    

    def checkFile(self):
        """Checking for needed columns in mg-rast metadata file"""
        try:
            self._tbl['id']
        except:
            raise IOError( 'MGRAST metaFile does not have "id" column' )


    def iterByRow(self):
        """Return iterator for processing table by row for mg-rast metadata table
        requires metaFile in pandas dataframe class
        
        Return:
        metagenome_id
        """
        reC = re.compile(r'((mgm)*\d\d\d\d\d\d\d\.\d)')
        
        for count, row in self._tbl.iterrows():
            metagenome_id = row['id']

            # check that metagenome ID is in correct format
            m = reC.match(metagenome_id)
            if not m:
                raise ValueError('id: "{0}" is not in correct format'.format(metagenome_id))
            else:
                metagenome_id = m.group(1)

            # determining sequencing platform
            platform = self.getPlatform(row)

            # yield
            yield {'ID' : metagenome_id, 'platform' : platform}
    

    def getPlatform(self, row):
        """Determining sequencing platform from metadata file

        Column(s) to check:
        seq_method
        
        Args:
        row -- row of pandas DataFrame
        """
        
        # check for column
        try: 
            row['seq_method']
        except KeyError as err:
            raise type(err)(err.message + '. "seq_meth" column not in metadata file!')

        # determine sequencing platform
        platform = None
        if re.search(r'454|pyro', row['seq_method'], flags=re.I) is not None:
            platform = '454'
        elif re.search( r'illumina', row['seq_method'], flags=re.I) is not None:
            platform = 'illumina'
        elif re.search( r'sanger', row['seq_method'], flags=re.I) is not None:
            platform = 'sanger'
        # return
        return platform


    def download(self, ID):
        """MG-RAST API request for downloading metagenome reads.
        Reads are downloaded as gzipped files.

        Kwargs:
        ID -- mg-rast metagenome ID

        Attrib edit:
        outFile -- string with downloaded file name
        """        

        # input check
        if ID is None:
            raise TypeError('ID cannot be None type')
        
        # trying each stage
        for stage in self.stages:
            # initialize url
            url = 'http://api.metagenomics.anl.gov/1/download/'
            url = url + ID + '?file={0}.1'.format(stage)            

            # send request to mgrast
            sys.stderr.write( 'For ID: "{0}", trying stage: "{1}"\n'.format(ID, stage) )
            sys.stderr.write( 'Sending request: "{0}"\n'.format(url) )
            req = requests.get(url)
            sys.stderr.write(' Request status: {0}\n'.format(str(req.status_code)))
            if req.status_code != 200:   # try next stage 
                sys.stderr.write('  Request != 200. Skipping!\n')
                continue

            # writing content to file
            outFile = ID + '_stage' + stage + '.fasta'
            d = zlib.decompressobj(16+zlib.MAX_WBITS)
            with open(outFile, 'wb') as fd:
                for chunk in req.iter_content(1000):
                    #fd.write(chunk)
                    fd.write( d.decompress( chunk) )
            sys.stderr.write(' File written: {0}\n'.format(outFile))

            # checking that content was written
            ## else: try next stage
            if os.stat(outFile)[6] != 0:
                self.outFile = outFile
            else:
                sys.stderr.write(' Requested content was empty! Skipping!\n')
                continue                      
        